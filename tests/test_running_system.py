"""Tests for evaluating the already-running application boundary."""

from __future__ import annotations

import json
import queue
from typing import Any

from akgentic_evals.events import (
    MessageObserved,
    RuntimeFailed,
    ToolCalled,
    ToolEvidenceObserved,
    ToolReturned,
)
from evals.harness.models import KnowledgeCaseInput
from evals.harness.running_system import (
    RUNNING_SYSTEM_CAPABILITIES,
    _normalize_event,
    _websocket_url,
    run_running_system_case,
)


def test_websocket_url_uses_running_backend_origin() -> None:
    assert (
        _websocket_url("http://localhost:8000")
        == "ws://localhost:8000/ws/chat"
    )
    assert _websocket_url("https://example.com/app") == "wss://example.com/ws/chat"


def test_normalize_events_preserves_correlated_tool_evidence() -> None:
    call = _normalize_event(
        {
            "kind": "tool_call",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "arguments": '{"query":"example"}',
        }
    )
    result = _normalize_event(
        {
            "kind": "tool_return",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "success": True,
        }
    )
    evidence = _normalize_event(
        {
            "kind": "tool_evidence",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "content": "Search Results: reviewed fact",
            "outcome": "success",
        }
    )
    message = _normalize_event(
        {
            "kind": "message",
            "sender": "@Manager",
            "recipient": "@Human",
            "type": "notification",
            "content": "Reviewed answer",
        }
    )

    assert isinstance(call, ToolCalled)
    assert call.arguments == {"query": "example"}
    assert isinstance(result, ToolReturned)
    assert result.success is True
    assert isinstance(evidence, ToolEvidenceObserved)
    assert evidence.content == "Search Results: reviewed fact"
    assert isinstance(message, MessageObserved)
    assert message.content == "Reviewed answer"


def test_running_system_declares_weak_transport_guarantees() -> None:
    assert RUNNING_SYSTEM_CAPABILITIES.request_correlation is False
    assert RUNNING_SYSTEM_CAPABILITIES.isolated_execution is False
    assert RUNNING_SYSTEM_CAPABILITIES.quiescence_detection is False
    assert RUNNING_SYSTEM_CAPABILITIES.trace_context is False


def test_application_errors_become_normalized_runtime_failures() -> None:
    event = _normalize_event({"kind": "error", "content": "routing failed"})

    assert isinstance(event, RuntimeFailed)
    assert event.error == "routing failed"


def test_running_system_case_uses_normalized_runtime(monkeypatch: Any) -> None:
    websocket = FakeWebSocket()
    monkeypatch.setattr(
        "evals.harness.running_system.connect",
        lambda url, open_timeout: websocket,
    )

    output = run_running_system_case(
        KnowledgeCaseInput(message="What is known?", timeout_seconds=1),
        system_url="http://localhost:8000",
    )

    assert output.final_response == "Reviewed answer"
    assert output.tool_invocations(tool_name="search_graph", successful=True)
    assert websocket.sent == ["What is known?"]
    assert websocket.closed


class FakeWebSocket:
    def __init__(self) -> None:
        self.events: queue.Queue[str] = queue.Queue()
        self.initial_received = False
        self.sent: list[str] = []
        self.closed = False

    def recv(self, timeout: float) -> str:
        if not self.initial_received:
            self.initial_received = True
            return json.dumps({"kind": "system", "content": "connected"})
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError from exc

    def send(self, payload: str) -> None:
        self.sent.append(payload)
        for event in (
            {
                "kind": "tool_call",
                "run_id": "run-1",
                "tool": "search_graph",
                "tool_call_id": "call-1",
                "arguments": '{"query":"example"}',
            },
            {
                "kind": "tool_return",
                "run_id": "run-1",
                "tool": "search_graph",
                "tool_call_id": "call-1",
                "success": True,
            },
            {
                "kind": "message",
                "sender": "@Manager",
                "recipient": "@Human",
                "type": "notification",
                "content": "Reviewed answer",
            },
        ):
            self.events.put(json.dumps(event))

    def close(self) -> None:
        self.closed = True
