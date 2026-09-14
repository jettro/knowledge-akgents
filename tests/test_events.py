"""Tests for evidence exposed through the application's WebSocket bridge."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import uuid4

from akgentic.core import ActorAddressProxy
from akgentic.core.messages.orchestrator import EventMessage
from akgentic.llm import LlmUsageEvent, ToolCallEvent, ToolReturnEvent

from knowledge_akgents.events import WebEventBridge


def _address(name: str) -> ActorAddressProxy:
    return ActorAddressProxy(
        {
            "__actor_address__": True,
            "agent_id": str(uuid.uuid4()),
            "name": name,
            "role": name.removeprefix("@"),
            "team_id": str(uuid.uuid4()),
            "squad_id": None,
            "is_user_proxy": False,
        }
    )


def test_bridge_publishes_correlated_tool_and_usage_events() -> None:
    published: list[dict[str, Any]] = []
    bridge = WebEventBridge(published.append)
    sender = _address("@Knowledge")

    bridge.on_message(
        EventMessage(
            sender=sender,
            event=ToolCallEvent(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="call-1",
                arguments='{"query":"example"}',
            ),
        )
    )
    bridge.on_message(
        EventMessage(
            sender=sender,
            event=ToolReturnEvent(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="call-1",
                success=True,
            ),
        )
    )
    bridge.on_message(
        EventMessage(
            sender=sender,
            event=LlmUsageEvent(
                run_id="run-1",
                model_name="test-model",
                provider_name="test-provider",
                input_tokens=10,
                output_tokens=5,
                cache_read_tokens=2,
                cache_write_tokens=0,
                requests=1,
            ),
        )
    )

    assert [event["kind"] for event in published] == [
        "tool_call",
        "tool_return",
        "llm_usage",
    ]
    assert published[0]["tool_call_id"] == "call-1"
    assert published[1]["tool_call_id"] == "call-1"
    assert published[1]["success"] is True


def test_bridge_suppresses_replayed_events_during_team_restore() -> None:
    published: list[dict[str, Any]] = []
    bridge = WebEventBridge(published.append)
    team_id = uuid4()
    message = EventMessage(
        team_id=team_id,
        sender=_address("@Knowledge"),
        event=ToolCallEvent(
            run_id="run-1",
            tool_name="search_graph",
            tool_call_id="call-1",
            arguments="{}",
        ),
    )

    bridge.set_restoring(team_id, True)
    bridge.on_message(message)
    bridge.set_restoring(team_id, False)
    bridge.on_message(message)

    assert [event["kind"] for event in published] == ["tool_call"]
