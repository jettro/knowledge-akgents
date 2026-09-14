"""Tests for evaluating the already-running application boundary."""

from __future__ import annotations

from evals.harness.running_system import _record_event, _websocket_url


def test_websocket_url_uses_running_backend_origin() -> None:
    assert (
        _websocket_url("http://localhost:8000")
        == "ws://localhost:8000/ws/chat"
    )
    assert _websocket_url("https://example.com/app") == "wss://example.com/ws/chat"


def test_record_event_collects_real_tool_evidence() -> None:
    messages = []
    tool_calls = []
    tool_returns = []
    tool_evidence = []
    llm_usage = []
    errors = []
    human_responses = []
    common = {
        "messages": messages,
        "tool_calls": tool_calls,
        "tool_returns": tool_returns,
        "tool_evidence": tool_evidence,
        "llm_usage": llm_usage,
        "errors": errors,
        "human_responses": human_responses,
    }

    _record_event(
        {
            "kind": "tool_call",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "arguments": '{"query":"example"}',
        },
        **common,
    )
    _record_event(
        {
            "kind": "tool_return",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "success": True,
        },
        **common,
    )
    _record_event(
        {
            "kind": "tool_evidence",
            "run_id": "run-1",
            "tool": "search_graph",
            "tool_call_id": "call-1",
            "content": "Search Results: reviewed fact",
            "outcome": "success",
        },
        **common,
    )
    _record_event(
        {
            "kind": "message",
            "sender": "@Manager",
            "recipient": "@Human",
            "type": "notification",
            "content": "Reviewed answer",
        },
        **common,
    )

    assert tool_calls[0].arguments == {"query": "example"}
    assert tool_returns[0].success is True
    assert tool_evidence[0].content == "Search Results: reviewed fact"
    assert human_responses == ["Reviewed answer"]
