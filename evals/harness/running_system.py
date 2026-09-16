"""Drive the running Knowledge Akgents application through WebSocket events."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from akgentic_evals.events import (
    AkgenticEvalEvent,
    MessageObserved,
    RuntimeFailed,
    RuntimeStopped,
    ToolCalled,
    ToolEvidenceObserved,
    ToolReturned,
    UsageObserved,
)
from akgentic_evals.models import AkgenticCaseOutput
from akgentic_evals.runtime import (
    ConversationTurn,
    EventHandler,
    RuntimeCapabilities,
    run_case_with_factory,
)
from evals.harness.models import KnowledgeCaseInput

RUNNING_SYSTEM_CAPABILITIES = RuntimeCapabilities(
    request_correlation=False,
    isolated_execution=False,
    quiescence_detection=False,
    trace_context=False,
)


def require_running_system(system_url: str) -> None:
    """Fail fast unless the configured Knowledge Akgents backend is reachable."""
    endpoint = f"{system_url.rstrip('/')}/api/status"
    try:
        with urlopen(endpoint, timeout=5) as response:
            payload = json.loads(response.read())
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not reach the running Knowledge Akgents system at {endpoint}: {exc}"
        ) from exc
    if payload.get("service") != "knowledge-akgents":
        raise ValueError(f"{endpoint} is not a Knowledge Akgents backend")


class RunningSystemRuntime:
    """Adapt the application's broadcast WebSocket to normalized events."""

    capabilities = RUNNING_SYSTEM_CAPABILITIES

    def __init__(self, system_url: str) -> None:
        self._system_url = system_url
        self._event_handler: EventHandler | None = None
        self._websocket: Any = None
        self._reader: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self, event_handler: EventHandler) -> None:
        self._event_handler = event_handler
        try:
            self._websocket = connect(_websocket_url(self._system_url), open_timeout=5)
            self._websocket.recv(timeout=5)  # initial connection/roster event
        except (OSError, ValueError, TimeoutError, ConnectionClosed) as exc:
            self._emit(RuntimeFailed(error=f"{type(exc).__name__}: {exc}"))
            return

        self._reader = threading.Thread(
            target=self._read_events,
            name="akgentic-eval-websocket",
            daemon=True,
        )
        self._reader.start()

    def send(self, turn: ConversationTurn) -> None:
        if self._websocket is None:
            return
        payload = (
            json.dumps({"text": turn.message, "target": turn.target})
            if turn.target
            else turn.message
        )
        try:
            self._websocket.send(payload)
        except (OSError, ConnectionClosed) as exc:
            self._emit(RuntimeFailed(error=f"{type(exc).__name__}: {exc}"))

    def shutdown(self) -> None:
        self._stopping.set()
        if self._websocket is not None:
            self._websocket.close()
            self._websocket = None
        if self._reader is not None:
            self._reader.join(timeout=1)
            self._reader = None

    def _read_events(self) -> None:
        assert self._websocket is not None
        while not self._stopping.is_set():
            try:
                raw = self._websocket.recv(timeout=0.2)
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("WebSocket event must be a JSON object")
                event = _normalize_event(data)
                if event is not None:
                    self._emit(event)
            except TimeoutError:
                continue
            except ConnectionClosed:
                if not self._stopping.is_set():
                    self._emit(RuntimeStopped())
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._emit(RuntimeFailed(error=f"{type(exc).__name__}: {exc}"))
                return

    def _emit(self, event: AkgenticEvalEvent) -> None:
        if self._event_handler is not None:
            self._event_handler(event)


class RunningSystemRuntimeFactory:
    def __init__(self, system_url: str) -> None:
        self._system_url = system_url

    @contextmanager
    def runtime(self, inputs: KnowledgeCaseInput) -> Iterator[RunningSystemRuntime]:
        yield RunningSystemRuntime(self._system_url)


def run_running_system_case(
    inputs: KnowledgeCaseInput,
    *,
    system_url: str,
) -> AkgenticCaseOutput:
    """Execute a case through the running backend's public WebSocket boundary."""
    return run_case_with_factory(
        inputs,
        RunningSystemRuntimeFactory(system_url),
    )


def _normalize_event(data: dict[str, Any]) -> AkgenticEvalEvent | None:
    kind = data.get("kind")
    if kind == "message":
        return MessageObserved(
            sender=data.get("sender"),
            recipient=data.get("recipient"),
            message_type=str(data.get("type", "")),
            content=str(data.get("content", "")),
        )
    if kind == "tool_call":
        arguments_raw = str(data.get("arguments", ""))
        try:
            arguments = json.loads(arguments_raw)
            parse_error = None
        except json.JSONDecodeError as exc:
            arguments = None
            parse_error = str(exc)
        return ToolCalled(
            run_id=str(data.get("run_id", "")),
            tool_name=str(data.get("tool", "")),
            tool_call_id=str(data.get("tool_call_id", "")),
            arguments_raw=arguments_raw,
            arguments=arguments,
            parse_error=parse_error,
        )
    if kind == "tool_return":
        return ToolReturned(
            run_id=str(data.get("run_id", "")),
            tool_name=str(data.get("tool", "")),
            tool_call_id=str(data.get("tool_call_id", "")),
            success=bool(data.get("success", False)),
        )
    if kind == "tool_evidence":
        return ToolEvidenceObserved(
            run_id=str(data.get("run_id", "")) or None,
            tool_name=str(data.get("tool", "")),
            tool_call_id=str(data.get("tool_call_id", "")),
            content=str(data.get("content", "")),
            outcome=str(data.get("outcome", "")),
        )
    if kind == "llm_usage":
        return UsageObserved(
            run_id=str(data.get("run_id", "")),
            model_name=str(data.get("model_name", "")),
            provider_name=str(data.get("provider_name", "")),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cache_read_tokens=int(data.get("cache_read_tokens", 0)),
            cache_write_tokens=int(data.get("cache_write_tokens", 0)),
            requests=int(data.get("requests", 0)),
        )
    if kind == "error":
        return RuntimeFailed(
            error=str(data.get("content", "Unknown application error"))
        )
    return None


def _websocket_url(system_url: str) -> str:
    parsed = urlsplit(system_url.rstrip("/"))
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError(f"Invalid running-system URL: {system_url!r}")
    scheme = {
        "http": "ws",
        "https": "wss",
        "ws": "ws",
        "wss": "wss",
    }[parsed.scheme]
    return urlunsplit((scheme, parsed.netloc, "/ws/chat", "", ""))
