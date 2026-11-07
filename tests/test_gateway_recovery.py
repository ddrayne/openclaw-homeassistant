"""Tests for connection recovery after a Gateway restart (HA-free).

These cover the failure modes seen in production when the Gateway (or the
reverse proxy in front of it) restarts:

* the WebSocket upgrade is rejected with HTTP 401/403 for a few seconds even
  though the token is valid, which used to end the connection loop forever;
* the receive task ends with ``ConnectionClosedError`` (close code 1012), which
  used to make ``disconnect()`` raise, so unload/reload/reconnect all failed and
  only a Home Assistant restart could clear the entry;
* a finished connection loop left ``_connect_task`` set, so ``connect()`` - and
  therefore the ``openclaw.reconnect`` service - became a silent no-op.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

_BASE = Path(__file__).parent.parent / "custom_components" / "openclaw"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.modules.setdefault("custom_components", ModuleType("custom_components"))
sys.modules.setdefault("custom_components.openclaw", ModuleType("custom_components.openclaw"))

_const = _load_module("custom_components.openclaw.const", _BASE / "const.py")
_exceptions = _load_module("custom_components.openclaw.exceptions", _BASE / "exceptions.py")
_device_auth = _load_module(
    "custom_components.openclaw.device_auth", _BASE / "device_auth.py"
)
gateway_module = _load_module(
    "custom_components.openclaw.gateway", _BASE / "gateway.py"
)

GatewayAuthenticationError = _exceptions.GatewayAuthenticationError
GatewayConnectionError = _exceptions.GatewayConnectionError
GatewayProtocol = gateway_module.GatewayProtocol


class FakeInvalidStatus(Exception):
    """Stand-in for websockets.exceptions.InvalidStatus (version independent)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.response = SimpleNamespace(status_code=status_code)


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.close_error: Exception | None = None

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        raise AssertionError("unexpected recv")

    async def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class FakeUpgrade:
    """Async context manager mimicking websockets.connect()."""

    def __init__(self, status_code: int | None = None) -> None:
        self._status_code = status_code
        self.websocket = FakeWebSocket()

    async def __aenter__(self) -> FakeWebSocket:
        if self._status_code is not None:
            raise FakeInvalidStatus(self._status_code)
        return self.websocket

    async def __aexit__(self, *exc_info) -> bool:
        return False


def scripted_connect(status_codes: list[int], calls: list[int]):
    """Return a connect() replacement replaying statuses, then succeeding."""

    remaining = list(status_codes)

    def factory(_uri: str, **_kwargs):
        calls.append(1)
        if remaining:
            return FakeUpgrade(remaining.pop(0))
        return FakeUpgrade()

    return factory


async def _raise(exc: BaseException) -> None:
    raise exc


class TestDisconnectRecovery:
    @pytest.mark.asyncio
    async def test_disconnect_survives_failed_receive_task(self) -> None:
        """A receive task that ended with 1012 must not break teardown."""
        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._receive_task = asyncio.create_task(
            _raise(GatewayConnectionError("received 1012 (service restart)"))
        )
        await asyncio.sleep(0)

        await protocol.disconnect()

        assert protocol._receive_task is None
        assert protocol._connect_task is None
        assert protocol._pending_requests == {}

    @pytest.mark.asyncio
    async def test_disconnect_survives_failed_connect_and_heartbeat_tasks(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._heartbeat_task = asyncio.create_task(_raise(RuntimeError("heartbeat")))
        protocol._connect_task = asyncio.create_task(_raise(RuntimeError("loop")))
        await asyncio.sleep(0)

        await protocol.disconnect()

        assert protocol._heartbeat_task is None
        assert protocol._connect_task is None

    @pytest.mark.asyncio
    async def test_disconnect_survives_websocket_close_error(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        websocket = FakeWebSocket()
        websocket.close_error = ConnectionResetError("already gone")
        protocol._websocket = websocket

        await protocol.disconnect()

        assert protocol._websocket is None

    @pytest.mark.asyncio
    async def test_disconnect_fails_pending_requests(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        future = asyncio.get_running_loop().create_future()
        protocol._pending_requests["req-1"] = future

        await protocol.disconnect()

        assert future.done()
        assert isinstance(future.exception(), GatewayConnectionError)


class TestConnectRevival:
    @pytest.mark.asyncio
    async def test_connect_after_loop_exit_starts_a_new_loop(self) -> None:
        """The reconnect service relies on this: a dead loop must not stick."""
        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._connection_loop = AsyncMock()  # returns immediately

        await protocol.connect()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert protocol._connect_task is None

        await protocol.connect()
        assert protocol._connect_task is not None

        protocol._connect_task.cancel()
        await asyncio.gather(protocol._connect_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_connect_is_idempotent_while_running(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        release = asyncio.Event()

        async def loop() -> None:
            await release.wait()

        protocol._connection_loop = loop

        await protocol.connect()
        first = protocol._connect_task
        await protocol.connect()

        assert protocol._connect_task is first

        release.set()
        await asyncio.wait_for(first, 5)

    @pytest.mark.asyncio
    async def test_connect_clears_stale_fatal_error(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._fatal_error = GatewayAuthenticationError("old failure")
        protocol._connection_loop = AsyncMock()

        await protocol.connect()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        assert protocol._fatal_error is None


class TestUpgradeAuthRetry:
    @pytest.mark.asyncio
    async def test_transient_auth_rejection_is_retried(self, monkeypatch) -> None:
        """401/403 during a Gateway restart must not kill the integration."""
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)

        calls: list[int] = []
        monkeypatch.setattr(
            gateway_module, "connect", scripted_connect([401, 403], calls)
        )

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock(side_effect=asyncio.CancelledError)
        protocol._heartbeat_loop = AsyncMock(side_effect=asyncio.CancelledError)
        on_connected = Mock()
        on_fatal_error = Mock()
        protocol._on_connected = on_connected
        protocol._on_fatal_error = on_fatal_error

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert len(calls) == 3
        assert delays == [5.0, 10.0]
        assert on_connected.call_count == 1
        assert on_fatal_error.call_count == 0
        assert protocol._fatal_error is None

    @pytest.mark.asyncio
    async def test_persistent_auth_rejection_ends_fatal(self, monkeypatch, caplog) -> None:
        """A real token problem is still reported, but only after bounded retries."""
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)

        calls: list[int] = []
        monkeypatch.setattr(
            gateway_module, "connect", scripted_connect([403] * 20, calls)
        )

        protocol = GatewayProtocol("localhost", 1, "token")
        on_fatal_error = Mock()
        protocol._on_fatal_error = on_fatal_error

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        expected_attempts = _const.UPGRADE_AUTH_RETRY_ATTEMPTS + 1
        assert len(calls) == expected_attempts
        assert on_fatal_error.call_count == 1
        assert isinstance(protocol._fatal_error, GatewayAuthenticationError)
        assert delays == [5.0, 10.0, 20.0, 40.0]
        assert "Gateway authentication failed (HTTP 403)" in caplog.text
        # The loop exited, so the reconnect service can start a fresh one.
        assert protocol._connect_task is None

    @pytest.mark.asyncio
    async def test_non_auth_upgrade_rejection_backs_off(self, monkeypatch) -> None:
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)

        calls: list[int] = []
        monkeypatch.setattr(
            gateway_module, "connect", scripted_connect([502, 503], calls)
        )

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock(side_effect=asyncio.CancelledError)
        protocol._heartbeat_loop = AsyncMock(side_effect=asyncio.CancelledError)

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert delays == [5.0, 10.0]
        assert len(calls) == 3


class TestUpgradeAuthStatus:
    @pytest.mark.asyncio
    async def test_status_tracks_rejections_until_handshake(self, monkeypatch) -> None:
        """Callers can tell a refused token from an unreachable Gateway."""
        protocol = GatewayProtocol("localhost", 1, "token")
        seen: list[int | None] = []

        async def fake_sleep(_delay: float) -> None:
            seen.append(protocol.upgrade_auth_status)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)
        monkeypatch.setattr(
            gateway_module, "connect", scripted_connect([401, 403], [])
        )
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock(side_effect=asyncio.CancelledError)
        protocol._heartbeat_loop = AsyncMock(side_effect=asyncio.CancelledError)

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert seen == [401, 403]
        assert protocol.upgrade_auth_status is None

    @pytest.mark.asyncio
    async def test_connect_clears_stale_status(self) -> None:
        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._upgrade_auth_status = 403
        protocol._connection_loop = AsyncMock()

        await protocol.connect()

        assert protocol.upgrade_auth_status is None
        await asyncio.gather(protocol._connect_task, return_exceptions=True)


class TestTlsContext:
    @pytest.mark.asyncio
    async def test_wss_context_is_built_once_off_the_event_loop(
        self, monkeypatch
    ) -> None:
        """Building the default context loads CA files: never on the loop."""
        import ssl
        import threading

        passed: list = []

        def factory(_uri: str, **kwargs):
            passed.append(kwargs.get("ssl"))
            # First attempt is rejected so the loop reconnects once.
            return FakeUpgrade(503 if len(passed) == 1 else None)

        built_on: list[int] = []
        real_create = ssl.create_default_context

        def counting_create(*args, **kwargs):
            built_on.append(threading.get_ident())
            return real_create(*args, **kwargs)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", _noop_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)
        monkeypatch.setattr(gateway_module, "connect", factory)
        monkeypatch.setattr(gateway_module.ssl, "create_default_context", counting_create)

        protocol = GatewayProtocol("localhost", 1, "token", use_ssl=True)
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock(side_effect=asyncio.CancelledError)
        protocol._heartbeat_loop = AsyncMock(side_effect=asyncio.CancelledError)

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert len(passed) == 2
        assert isinstance(passed[0], ssl.SSLContext)
        assert passed[0] is passed[1]  # reused across reconnects
        assert len(built_on) == 1
        assert built_on[0] != threading.get_ident()

    @pytest.mark.asyncio
    async def test_plain_ws_passes_no_ssl_argument(self, monkeypatch) -> None:
        """websockets rejects any ssl argument for a ws:// URI."""
        seen: list[dict] = []

        def factory(_uri: str, **kwargs):
            seen.append(kwargs)
            return FakeUpgrade()

        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)
        monkeypatch.setattr(gateway_module, "connect", factory)
        protocol = GatewayProtocol("localhost", 1, "token", use_ssl=False)
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock(side_effect=asyncio.CancelledError)
        protocol._heartbeat_loop = AsyncMock(side_effect=asyncio.CancelledError)

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert "ssl" not in seen[0]


class TestRetryBackoff:
    def test_delay_grows_then_caps(self) -> None:
        protocol = GatewayProtocol("localhost", 1, None)
        delays = [protocol._retry_delay(n) for n in range(1, 8)]

        assert delays == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0]

    @pytest.mark.parametrize("failures", [1025, 10 ** 6, 2 ** 40])
    def test_delay_saturates_instead_of_overflowing(self, failures: int) -> None:
        """An OverflowError here would stop recovery without a fatal error."""
        protocol = GatewayProtocol("localhost", 1, None)

        assert protocol._retry_delay(failures) == _const.RETRY_MAX_SECONDS


class TestLoopTeardown:
    @pytest.mark.asyncio
    async def test_stale_receive_task_does_not_override_fatal_auth_stop(
        self, monkeypatch
    ) -> None:
        """A fatal stop must stay fatal even if a helper task already failed."""
        monkeypatch.setattr(gateway_module.asyncio, "sleep", _noop_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)

        calls: list[int] = []
        monkeypatch.setattr(gateway_module, "connect", scripted_connect([], calls))

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock(
            side_effect=GatewayAuthenticationError("invalid token")
        )
        protocol._receive_task = asyncio.create_task(
            _raise(GatewayConnectionError("received 1012 (service restart)"))
        )
        await asyncio.sleep(0)
        on_fatal_error = Mock()
        protocol._on_fatal_error = on_fatal_error

        await protocol.connect()
        await asyncio.wait_for(protocol._connect_task, 5)

        assert len(calls) == 1
        assert on_fatal_error.call_count == 1
        assert isinstance(protocol._fatal_error, GatewayAuthenticationError)
        assert protocol._receive_task is None
        assert protocol._heartbeat_task is None

    @pytest.mark.asyncio
    async def test_clean_socket_close_pauses_before_reconnecting(
        self, monkeypatch
    ) -> None:
        """A receive loop that returns normally must not spin immediately."""
        real_sleep = asyncio.sleep
        delays: list[float] = []

        async def fake_sleep(delay: float) -> None:
            delays.append(delay)
            await real_sleep(0)

        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)

        calls: list[int] = []
        monkeypatch.setattr(gateway_module, "connect", scripted_connect([], calls))

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock()  # returns immediately
        protocol._heartbeat_loop = AsyncMock()

        await protocol.connect()
        task = protocol._connect_task
        for _ in range(200):
            await real_sleep(0)
            if len(delays) >= 2:
                break

        await protocol.disconnect()
        await asyncio.gather(task, return_exceptions=True)

        assert delays[:2] == [5.0, 10.0]
        # Each reconnect attempt is preceded by a pause, so the count of
        # attempts can never outrun the count of recorded delays.
        assert len(calls) >= 2

    @pytest.mark.asyncio
    async def test_cancelling_the_loop_stops_it_during_helper_teardown(
        self, monkeypatch
    ) -> None:
        """Caller cancellation must not be swallowed by the helper wait.

        The loop's ``finally`` waits on helper tasks. If that wait treats the
        *loop's* cancellation as the helper's, the loop keeps running after
        being cancelled, no longer tracked by ``_connect_task`` - which is how a
        reconnect could leave a second connection loop behind.
        """
        monkeypatch.setattr(gateway_module, "TASK_STOP_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)
        monkeypatch.setattr(gateway_module, "connect", scripted_connect([], []))

        release = asyncio.Event()

        async def stubborn() -> None:
            while not release.is_set():
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    continue  # deliberately ignores cancellation

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock()
        protocol._receive_loop = AsyncMock()  # ends, so the loop tears down
        protocol._heartbeat_loop = stubborn

        try:
            await protocol.connect()
            task = protocol._connect_task
            for _ in range(50):
                await asyncio.sleep(0)
                if not task.done():
                    break
            await asyncio.sleep(0)

            task.cancel()
            await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), timeout=1
            )

            assert task.done()
        finally:
            release.set()
            for leftover in asyncio.all_tasks():
                if leftover is not asyncio.current_task():
                    leftover.cancel()
            await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_disconnect_stops_helpers_and_loop(self) -> None:
        """Teardown must leave no tracked task behind (no orphan heartbeat)."""
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(gateway_module, "InvalidStatus", FakeInvalidStatus)
        forever = asyncio.Event()

        async def block() -> None:
            await forever.wait()

        monkeypatch.setattr(gateway_module, "connect", scripted_connect([], []))

        protocol = GatewayProtocol("localhost", 1, "token")
        protocol._handshake = AsyncMock()
        protocol._receive_loop = block
        protocol._heartbeat_loop = block

        await protocol.connect()
        for _ in range(50):
            await asyncio.sleep(0)
            if protocol._receive_task is not None and protocol._heartbeat_task is not None:
                break

        await protocol.disconnect()

        assert protocol._receive_task is None
        assert protocol._heartbeat_task is None
        assert protocol._connect_task is None
        assert not protocol.connected
        forever.set()
        monkeypatch.undo()


async def _noop_sleep(_delay: float) -> None:
    """Replace asyncio.sleep without awaiting it (it is patched globally)."""
    return None
