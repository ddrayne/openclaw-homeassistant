"""Tests for background agent work: grace-period race + report-back.

Long-running agent requests must not end in "the response took too long".
Instead the conversation entity races the run against a grace timer:

- First content within grace -> answer inline exactly as before.
- Grace expires silent -> speak a holding phrase, detach the run to a
  background task, and announce the result on the originating satellite
  (fallback: the configured proactive satellite) when it finishes.
"""

import asyncio
from types import SimpleNamespace

import pytest

from tests._conversation_loader import load_conversation_module

# Two module instances so both fast-path presentations are covered:
# streaming-capable HA (response_stream) and plain-result HA.
_conv_stream = load_conversation_module(streaming="primary")
_conv_plain = load_conversation_module(streaming="none")

RUN_ID = "r1"


def _output_event(run_id: str, text: str) -> dict:
    return {"payload": {"runId": run_id, "output": text, "stream": "assistant"}}


def _done_event(run_id: str) -> dict:
    return {
        "payload": {
            "runId": run_id,
            "stream": "lifecycle",
            "data": {"phase": "end"},
        }
    }


def _error_event(run_id: str, message: str = "boom") -> dict:
    return {
        "payload": {
            "runId": run_id,
            "stream": "lifecycle",
            "data": {"phase": "error", "error": message},
        }
    }


class _FakeServices:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))


class _FakeHass:
    def __init__(self) -> None:
        self.services = _FakeServices()

    def async_create_background_task(self, coro, name=None):
        return asyncio.create_task(coro)


class _FakeEntry:
    entry_id = "e1"
    data: dict = {}

    def __init__(self, options: dict) -> None:
        self.options = options


def _make_env(mod, options: dict, timeout: float = 5.0):
    """Real client with a stubbed gateway transport; events drive the run."""
    client = mod.OpenClawGatewayClient("localhost", 1, None, timeout=timeout)

    async def _fake_send_request(method=None, params=None, timeout=None, **_kw):
        return {"payload": {"runId": RUN_ID}}

    client._gateway.send_request = _fake_send_request
    entity = mod.OpenClawConversationEntity(_FakeEntry(options), client)
    entity.hass = _FakeHass()
    return client, entity


def _user_input(mod, device_id=None):
    return SimpleNamespace(
        text="summarize my email",
        language="en",
        agent_id="agent",
        conversation_id="c1",
        device_id=device_id,
    )


def _start(mod, entity, device_id=None):
    user_input = _user_input(mod, device_id)
    chat_log = mod.conversation.ChatLog()
    return asyncio.create_task(
        entity._async_handle_message(user_input, chat_log)
    )


async def _settle(seconds: float = 0.1) -> None:
    """Give detached background tasks time to drain and announce."""
    await asyncio.sleep(seconds)


class TestFastPath:
    """First content within grace -> inline answer, no announce."""

    @pytest.mark.asyncio
    async def test_streaming_result_streams_inline(self) -> None:
        client, entity = _make_env(_conv_stream, {"background_grace": 0.5})
        task = _start(_conv_stream, entity)
        await asyncio.sleep(0.01)
        client._handle_agent_event(_output_event(RUN_ID, "Quick answer"))
        result = await asyncio.wait_for(task, 2)

        assert getattr(result, "response_stream", None) is not None
        client._handle_agent_event(_done_event(RUN_ID))
        chunks = [c async for c in result.response_stream]
        assert chunks == ["Quick answer"]
        assert result.response.speech == "Quick answer"
        assert entity.hass.services.calls == []

    @pytest.mark.asyncio
    async def test_plain_result_waits_for_completion(self) -> None:
        client, entity = _make_env(_conv_plain, {"background_grace": 0.5})
        task = _start(_conv_plain, entity)
        await asyncio.sleep(0.01)
        client._handle_agent_event(_output_event(RUN_ID, "Quick answer"))
        client._handle_agent_event(_done_event(RUN_ID))
        result = await asyncio.wait_for(task, 2)

        assert result.response.speech == "Quick answer"
        assert entity.hass.services.calls == []

    @pytest.mark.asyncio
    async def test_fast_path_question_keeps_conversation_open(self) -> None:
        client, entity = _make_env(_conv_plain, {"background_grace": 0.5})
        task = _start(_conv_plain, entity)
        await asyncio.sleep(0.01)
        client._handle_agent_event(_output_event(RUN_ID, "Want details?"))
        client._handle_agent_event(_done_event(RUN_ID))
        result = await asyncio.wait_for(task, 2)

        assert result.continue_conversation is True

    @pytest.mark.asyncio
    async def test_run_completing_empty_within_grace_does_not_hang(self) -> None:
        # The completion sentinel may be the first queue item (empty run).
        # Peeking it must not leave a later drain waiting forever.
        client, entity = _make_env(_conv_plain, {"background_grace": 0.5})
        task = _start(_conv_plain, entity)
        await asyncio.sleep(0.01)
        client._handle_agent_event(_done_event(RUN_ID))
        result = await asyncio.wait_for(task, 2)

        assert result.response.speech == ""
        assert entity.hass.services.calls == []

    @pytest.mark.asyncio
    async def test_run_erroring_within_grace_returns_error_result(self) -> None:
        client, entity = _make_env(_conv_plain, {"background_grace": 0.5})
        task = _start(_conv_plain, entity)
        await asyncio.sleep(0.01)
        client._handle_agent_event(_error_event(RUN_ID))
        result = await asyncio.wait_for(task, 2)

        assert "error" in result.response.speech.lower()
        assert entity.hass.services.calls == []


class TestSlowPath:
    """Grace expires silent -> holding phrase now, announce later."""

    @pytest.mark.asyncio
    async def test_holding_phrase_then_announce_on_proactive_satellite(
        self,
    ) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
            },
        )
        task = _start(_conv_plain, entity)
        result = await asyncio.wait_for(task, 2)

        assert result.response.speech == _conv_plain.DEFAULT_HOLDING_PHRASE
        assert entity.hass.services.calls == []

        client._handle_agent_event(_output_event(RUN_ID, "Found 5 emails"))
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()

        calls = entity.hass.services.calls
        assert len(calls) == 1
        domain, service, data, _ = calls[0]
        assert (domain, service) == ("assist_satellite", "announce")
        assert data["entity_id"] == "assist_satellite.kitchen"
        assert data["message"] == "Found 5 emails"

    @pytest.mark.asyncio
    async def test_custom_holding_phrase(self) -> None:
        client, entity = _make_env(
            _conv_plain,
            {"background_grace": 0.05, "holding_phrase": "Working on it, boss."},
        )
        task = _start(_conv_plain, entity)
        result = await asyncio.wait_for(task, 2)
        assert result.response.speech == "Working on it, boss."
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()

    @pytest.mark.asyncio
    async def test_report_targets_originating_satellite(
        self, monkeypatch
    ) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
            },
        )
        entries = [
            SimpleNamespace(domain="sensor", entity_id="sensor.study_temp"),
            SimpleNamespace(
                domain="assist_satellite", entity_id="assist_satellite.study"
            ),
        ]
        monkeypatch.setattr(
            _conv_plain.er, "async_get", lambda _hass: "registry"
        )
        monkeypatch.setattr(
            _conv_plain.er,
            "async_entries_for_device",
            lambda _reg, device_id: entries if device_id == "dev-1" else [],
        )

        task = _start(_conv_plain, entity, device_id="dev-1")
        await asyncio.wait_for(task, 2)
        client._handle_agent_event(_output_event(RUN_ID, "Done"))
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()

        calls = entity.hass.services.calls
        assert len(calls) == 1
        assert calls[0][2]["entity_id"] == "assist_satellite.study"

    @pytest.mark.asyncio
    async def test_no_satellite_anywhere_drops_report(self) -> None:
        client, entity = _make_env(_conv_plain, {"background_grace": 0.05})
        task = _start(_conv_plain, entity)
        await asyncio.wait_for(task, 2)
        client._handle_agent_event(_output_event(RUN_ID, "Done"))
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()
        assert entity.hass.services.calls == []

    @pytest.mark.asyncio
    async def test_detached_error_announces_failure_phrase(self) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
            },
        )
        task = _start(_conv_plain, entity)
        await asyncio.wait_for(task, 2)
        client._handle_agent_event(_error_event(RUN_ID))
        await _settle()

        calls = entity.hass.services.calls
        assert len(calls) == 1
        assert calls[0][2]["message"] == _conv_plain.BACKGROUND_ERROR_PHRASE

    @pytest.mark.asyncio
    async def test_detached_timeout_announces_timeout_phrase(self) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
            },
            timeout=0.05,
        )
        task = _start(_conv_plain, entity)
        await asyncio.wait_for(task, 2)
        # No further events: the per-chunk timeout expires in the background.
        await _settle(0.3)

        calls = entity.hass.services.calls
        assert len(calls) == 1
        assert calls[0][2]["message"] == _conv_plain.BACKGROUND_TIMEOUT_PHRASE

    @pytest.mark.asyncio
    async def test_report_applies_emoji_strip(self) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
                "strip_emojis": True,
            },
        )
        task = _start(_conv_plain, entity)
        await asyncio.wait_for(task, 2)
        client._handle_agent_event(
            _output_event(RUN_ID, "All done \U0001F600")
        )
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()

        calls = entity.hass.services.calls
        assert len(calls) == 1
        assert calls[0][2]["message"] == "All done"


class TestOlderHomeAssistant:
    """Cores without async_create_background_task still get report-back."""

    @pytest.mark.asyncio
    async def test_falls_back_to_async_create_task(self) -> None:
        client, entity = _make_env(
            _conv_plain,
            {
                "background_grace": 0.05,
                "proactive_satellite": "assist_satellite.kitchen",
            },
        )

        class _OldHass:
            def __init__(self) -> None:
                self.services = _FakeServices()

            def async_create_task(self, coro):
                return asyncio.create_task(coro)

        entity.hass = _OldHass()
        task = _start(_conv_plain, entity)
        result = await asyncio.wait_for(task, 2)
        assert result.response.speech == _conv_plain.DEFAULT_HOLDING_PHRASE

        client._handle_agent_event(_output_event(RUN_ID, "Done"))
        client._handle_agent_event(_done_event(RUN_ID))
        await _settle()
        calls = entity.hass.services.calls
        assert len(calls) == 1
        assert calls[0][2]["message"] == "Done"


class TestBackgroundDisabled:
    """background_enabled=False restores the legacy timeout behavior."""

    @pytest.mark.asyncio
    async def test_timeout_speaks_legacy_message(self) -> None:
        client, entity = _make_env(
            _conv_plain, {"background_enabled": False}, timeout=0.05
        )
        task = _start(_conv_plain, entity)
        result = await asyncio.wait_for(task, 2)

        assert (
            result.response.speech
            == "The response took too long. Please try again."
        )
        await _settle()
        assert entity.hass.services.calls == []
