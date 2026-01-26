"""The Clawd integration."""

import asyncio
import inspect
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MODEL,
    CONF_SESSION_KEY,
    CONF_STRIP_EMOJIS,
    CONF_THINKING,
    CONF_TIMEOUT,
    CONF_TTS_MAX_CHARS,
    CONF_USE_SSL,
    DEFAULT_MODEL,
    DEFAULT_SESSION_KEY,
    DEFAULT_STRIP_EMOJIS,
    DEFAULT_THINKING,
    DEFAULT_TIMEOUT,
    DEFAULT_TTS_MAX_CHARS,
    DEFAULT_USE_SSL,
    DOMAIN,
    EVENT_CRON_ADDED,
    EVENT_CRON_REMOVED,
    EVENT_CRON_RUN,
    EVENT_TASK_COMPLETE,
)
from .gateway_client import ClawdGatewayClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION, Platform.SENSOR]
SERVICE_RECONNECT = "reconnect"
SERVICE_SET_SESSION = "set_session"
SERVICE_SPAWN_TASK = "spawn_task"
SERVICE_CRON_ADD = "cron_add"
SERVICE_CRON_REMOVE = "cron_remove"
SERVICE_CRON_RUN = "cron_run"
_SERVICE_REGISTERED = "_service_registered"
_RECONNECT_SCHEMA = vol.Schema({vol.Optional("entry_id"): str})
_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_KEY): vol.All(str, vol.Length(min=1)),
        vol.Optional("entry_id"): str,
    }
)
_SPAWN_SCHEMA = vol.Schema(
    {
        vol.Required("task"): vol.All(str, vol.Length(min=1)),
        vol.Optional("label"): str,
        vol.Optional("cleanup", default="delete"): vol.In(["delete", "keep"]),
        vol.Optional("timeout_seconds"): vol.All(int, vol.Range(min=1, max=3600)),
        vol.Optional("entry_id"): str,
    }
)
_CRON_ADD_SCHEMA = vol.Schema(
    {
        vol.Required("schedule"): vol.All(str, vol.Length(min=1)),
        vol.Required("text"): vol.All(str, vol.Length(min=1)),
        vol.Optional("context_messages"): vol.All(int, vol.Range(min=0, max=10)),
        vol.Optional("entry_id"): str,
    }
)
_CRON_REMOVE_SCHEMA = vol.Schema(
    {vol.Required("job_id"): vol.All(str, vol.Length(min=1)), vol.Optional("entry_id"): str}
)
_CRON_RUN_SCHEMA = vol.Schema(
    {
        vol.Required("job_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("mode", default="now"): vol.In(["now"]),
        vol.Optional("entry_id"): str,
    }
)

_OPTION_KEYS = {
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_TIMEOUT,
    CONF_SESSION_KEY,
    CONF_MODEL,
    CONF_THINKING,
    CONF_STRIP_EMOJIS,
    CONF_TTS_MAX_CHARS,
}


async def _async_request_json(
    hass: HomeAssistant,
    entry: ConfigEntry,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a JSON request to the Gateway REST API."""
    from homeassistant.helpers import aiohttp_client

    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]
    port = data[CONF_PORT]
    use_ssl = data.get(CONF_USE_SSL, DEFAULT_USE_SSL)
    token = data.get(CONF_TOKEN)

    scheme = "https" if use_ssl else "http"
    url = f"{scheme}://{host}:{port}/{path.lstrip('/')}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    session = aiohttp_client.async_get_clientsession(hass)
    async with session.request(
        method,
        url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=10,
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Gateway request failed with status {resp.status}")
        payload = await resp.json()

    if not payload.get("ok", True):
        raise RuntimeError(payload.get("error", "Gateway request failed"))

    return payload


async def _async_iter_target_entries(
    hass: HomeAssistant, entry_id: str | None
) -> list[ConfigEntry]:
    """Resolve target config entries."""
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            _LOGGER.warning("Requested entry not found: %s", entry_id)
            return []
        return [entry]
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id in hass.data.get(DOMAIN, {})
    ]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clawd from a config entry."""
    _LOGGER.info("Setting up Clawd integration")

    # Migrate option-like keys from data to options for existing entries.
    if not entry.options:
        migrated = {
            key: entry.data.get(key)
            for key in _OPTION_KEYS
            if key in entry.data
        }
        if migrated:
            hass.config_entries.async_update_entry(entry, options=migrated)

    options = entry.options

    # Create Gateway client with config from entry.data
    gateway_client = ClawdGatewayClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=options.get(CONF_TOKEN, entry.data.get(CONF_TOKEN)),
        use_ssl=options.get(
            CONF_USE_SSL, entry.data.get(CONF_USE_SSL, DEFAULT_USE_SSL)
        ),
        timeout=options.get(
            CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        ),
        session_key=options.get(
            CONF_SESSION_KEY,
            entry.data.get(CONF_SESSION_KEY, DEFAULT_SESSION_KEY),
        ),
        model=options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL)),
        thinking=options.get(
            CONF_THINKING, entry.data.get(CONF_THINKING, DEFAULT_THINKING)
        ),
    )

    # Connect to Gateway
    try:
        await gateway_client.connect()
        _LOGGER.info(
            "Connected to Clawd Gateway at %s:%s",
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
        )
    except Exception as err:
        _LOGGER.error("Failed to connect to Gateway: %s", err)
        return False

    # Store client in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = gateway_client

    if not hass.data[DOMAIN].get(_SERVICE_REGISTERED):
        async def _async_handle_reconnect(call) -> None:
            entry_id = call.data.get("entry_id")
            clients = hass.data.get(DOMAIN, {})

            if entry_id:
                target = clients.get(entry_id)
                if not target:
                    _LOGGER.warning("Reconnect requested for unknown entry: %s", entry_id)
                    return
                targets = [target]
            else:
                targets = [
                    client
                    for key, client in clients.items()
                    if key != _SERVICE_REGISTERED
                ]

            for client in targets:
                await client.disconnect()
                await client.connect()

        hass.services.async_register(
            DOMAIN, SERVICE_RECONNECT, _async_handle_reconnect, schema=_RECONNECT_SCHEMA
        )

        async def _async_handle_set_session(call) -> None:
            entry_id = call.data.get("entry_id")
            session_key = call.data[CONF_SESSION_KEY]
            clients = hass.data.get(DOMAIN, {})

            if entry_id:
                target = clients.get(entry_id)
                if not target:
                    _LOGGER.warning(
                        "Session update requested for unknown entry: %s",
                        entry_id,
                    )
                    return
                targets = [target]
            else:
                targets = [
                    client
                    for key, client in clients.items()
                    if key != _SERVICE_REGISTERED
                ]

            for client in targets:
                client.set_session_key(session_key)

        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SESSION,
            _async_handle_set_session,
            schema=_SESSION_SCHEMA,
        )

        async def _async_handle_spawn_task(call) -> None:
            entry_id = call.data.get("entry_id")
            clients = hass.data.get(DOMAIN, {})
            task = call.data["task"]
            label = call.data.get("label")
            cleanup = call.data.get("cleanup", "delete")
            timeout_seconds = call.data.get("timeout_seconds")

            if entry_id:
                target = clients.get(entry_id)
                if not target:
                    _LOGGER.warning(
                        "Spawn task requested for unknown entry: %s",
                        entry_id,
                    )
                    return
                targets = [entry_id]
            else:
                targets = [
                    key
                    for key in clients
                    if key != _SERVICE_REGISTERED
                ]

            for target_entry_id in targets:
                entry = hass.config_entries.async_get_entry(target_entry_id)
                if entry is None:
                    _LOGGER.warning(
                        "Spawn task requested for missing entry: %s",
                        target_entry_id,
                    )
                    continue
                try:
                    payload = await _async_request_json(
                        hass,
                        entry,
                        "POST",
                        "sessions/spawn",
                        json_body={
                            "task": task,
                            "cleanup": cleanup,
                            **({"label": label} if label else {}),
                            **(
                                {"timeoutSeconds": timeout_seconds}
                                if timeout_seconds
                                else {}
                            ),
                        },
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "Failed to spawn task for %s: %s",
                        target_entry_id,
                        err,
                    )
                    continue
                payload = payload.get("payload", payload)
                session_key = payload.get("sessionKey")
                spawn_label = payload.get("label", label)
                _LOGGER.info(
                    "Spawned task %s (session: %s)",
                    spawn_label or "task",
                    session_key,
                )

                if not session_key:
                    continue

                async def _poll_status(
                    poll_entry: ConfigEntry,
                    spawn_session_key: str,
                    spawn_label_value: str | None,
                    max_wait: int,
                ) -> None:
                    start = asyncio.get_running_loop().time()
                    while True:
                        try:
                            status_payload = await _async_request_json(
                                hass,
                                poll_entry,
                                "GET",
                                f"sessions/{spawn_session_key}/status",
                            )
                        except Exception as err:  # pylint: disable=broad-except
                            _LOGGER.warning(
                                "Failed to fetch spawn status for %s: %s",
                                spawn_session_key,
                                err,
                            )
                            return
                        status_payload = status_payload.get("payload", status_payload)
                        status = status_payload.get("status")
                        if status and status not in ("running", "pending"):
                            response_text = None
                            try:
                                history_payload = await _async_request_json(
                                    hass,
                                    poll_entry,
                                    "GET",
                                    f"sessions/{spawn_session_key}/history",
                                    params={"limit": "1"},
                                )
                                history_payload = history_payload.get(
                                    "payload", history_payload
                                )
                                messages = history_payload.get("messages", [])
                                if messages:
                                    response_text = messages[-1].get("content")
                            except Exception as err:  # pylint: disable=broad-except
                                _LOGGER.debug(
                                    "Failed to fetch spawn history for %s: %s",
                                    spawn_session_key,
                                    err,
                                )

                            hass.bus.async_fire(
                                EVENT_TASK_COMPLETE,
                                {
                                    "session_key": spawn_session_key,
                                    "label": spawn_label_value,
                                    "status": status,
                                    "response": response_text,
                                    "duration": status_payload.get("duration"),
                                    "model": status_payload.get("model"),
                                    "usage": status_payload.get("usage"),
                                },
                            )
                            return

                        if asyncio.get_running_loop().time() - start >= max_wait:
                            hass.bus.async_fire(
                                EVENT_TASK_COMPLETE,
                                {
                                    "session_key": spawn_session_key,
                                    "label": spawn_label_value,
                                    "status": "timeout",
                                    "response": None,
                                    "duration": status_payload.get("duration"),
                                    "model": status_payload.get("model"),
                                    "usage": status_payload.get("usage"),
                                },
                            )
                            return

                        await asyncio.sleep(5)

                max_wait = timeout_seconds or 3600
                hass.async_create_task(
                    _poll_status(entry, session_key, spawn_label, max_wait)
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_SPAWN_TASK,
            _async_handle_spawn_task,
            schema=_SPAWN_SCHEMA,
        )

        async def _async_handle_cron_add(call) -> None:
            entry_id = call.data.get("entry_id")
            schedule = call.data["schedule"]
            text = call.data["text"]
            context_messages = call.data.get("context_messages")

            entries = await _async_iter_target_entries(hass, entry_id)
            for target_entry in entries:
                try:
                    payload = await _async_request_json(
                        hass,
                        target_entry,
                        "POST",
                        "cron/add",
                        json_body={
                            "schedule": schedule,
                            "text": text,
                            **(
                                {"contextMessages": context_messages}
                                if context_messages is not None
                                else {}
                            ),
                        },
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "Failed to add cron job for %s: %s",
                        target_entry.entry_id,
                        err,
                    )
                    continue

                payload = payload.get("payload", payload)
                hass.bus.async_fire(
                    EVENT_CRON_ADDED,
                    {
                        "job_id": payload.get("jobId"),
                        "schedule": schedule,
                        "text": text,
                    },
                )

        async def _async_handle_cron_remove(call) -> None:
            entry_id = call.data.get("entry_id")
            job_id = call.data["job_id"]

            entries = await _async_iter_target_entries(hass, entry_id)
            for target_entry in entries:
                try:
                    await _async_request_json(
                        hass,
                        target_entry,
                        "DELETE",
                        f"cron/{job_id}",
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "Failed to remove cron job for %s: %s",
                        target_entry.entry_id,
                        err,
                    )
                    continue

                hass.bus.async_fire(
                    EVENT_CRON_REMOVED,
                    {"job_id": job_id},
                )

        async def _async_handle_cron_run(call) -> None:
            entry_id = call.data.get("entry_id")
            job_id = call.data["job_id"]
            mode = call.data.get("mode", "now")

            entries = await _async_iter_target_entries(hass, entry_id)
            for target_entry in entries:
                try:
                    payload = await _async_request_json(
                        hass,
                        target_entry,
                        "POST",
                        f"cron/{job_id}/run",
                        json_body={"mode": mode},
                    )
                except Exception as err:  # pylint: disable=broad-except
                    _LOGGER.warning(
                        "Failed to run cron job for %s: %s",
                        target_entry.entry_id,
                        err,
                    )
                    continue

                payload = payload.get("payload", payload)
                hass.bus.async_fire(
                    EVENT_CRON_RUN,
                    {
                        "job_id": job_id,
                        "executed": payload.get("executed"),
                        "response": payload.get("response"),
                    },
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_CRON_ADD,
            _async_handle_cron_add,
            schema=_CRON_ADD_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_CRON_REMOVE,
            _async_handle_cron_remove,
            schema=_CRON_REMOVE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_CRON_RUN,
            _async_handle_cron_run,
            schema=_CRON_RUN_SCHEMA,
        )
        hass.data[DOMAIN][_SERVICE_REGISTERED] = True

    # Forward setup to conversation platform
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        _LOGGER.exception("Failed to set up conversation platform")
        await gateway_client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return False

    # Register reload listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Clawd integration")

    # Get client before unloading
    gateway_client: ClawdGatewayClient | None = (
        hass.data.get(DOMAIN, {}).get(entry.entry_id)
    )
    if gateway_client is None:
        _LOGGER.debug(
            "Entry not found in hass.data during unload: %s", entry.entry_id
        )

    # Unload conversation platform even if the client was already cleared.
    try:
        unload_result = hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )
        if inspect.isawaitable(unload_result):
            unload_ok = await unload_result
        else:
            unload_ok = bool(unload_result) if unload_result is not None else True
    except ValueError:
        _LOGGER.warning(
            "Conversation platform was not loaded for entry: %s", entry.entry_id
        )
        unload_ok = True

    # Always disconnect and cleanup, even if unload failed
    if gateway_client is not None:
        await gateway_client.disconnect()
        _LOGGER.info("Disconnected from Clawd Gateway")
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    try:
        await async_unload_entry(hass, entry)
    except Exception:
        _LOGGER.exception(
            "Failed to unload entry during reload: %s", entry.entry_id
        )
    await async_setup_entry(hass, entry)
