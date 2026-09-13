"""Tests for the evaluation spike's event collection."""

from __future__ import annotations

import argparse
import uuid

import pytest
from akgentic.agent import AgentMessage
from akgentic.core import ActorAddressProxy
from akgentic.core.messages.orchestrator import ErrorMessage, EventMessage, SentMessage
from akgentic.llm import LlmUsageEvent, ToolCallEvent, ToolReturnEvent

from evals.cli import positive_int
from evals.collector import EvaluationEventCollector
from evals.datasets.retrieval_only import build_retrieval_only_dataset
from evals.observability_spike import _select_case


def _address(name: str, *, is_user_proxy: bool = False) -> ActorAddressProxy:
    identifier = str(uuid.uuid4())
    return ActorAddressProxy(
        {
            "__actor_address__": True,
            "agent_id": identifier,
            "name": name,
            "role": name.removeprefix("@"),
            "team_id": str(uuid.uuid4()),
            "squad_id": None,
            "is_user_proxy": is_user_proxy,
        }
    )


def test_collector_correlates_tool_calls_and_returns() -> None:
    collector = EvaluationEventCollector()
    agent = _address("@WebIngest")

    collector.on_message(
        EventMessage(
            sender=agent,
            event=ToolCallEvent(
                run_id="run-1",
                tool_name="web_fetch",
                tool_call_id="call-1",
                arguments='{"url": "https://coenradie.com/about"}',
            ),
        )
    )
    collector.on_message(
        EventMessage(
            sender=agent,
            event=ToolReturnEvent(
                run_id="run-1",
                tool_name="web_fetch",
                tool_call_id="call-1",
                success=True,
            ),
        )
    )

    output = collector.wait(0)

    assert output.human_responses == []
    assert output.tool_calls[0].arguments == {"url": "https://coenradie.com/about"}
    assert output.tool_calls[0].parse_error is None
    assert output.tool_returns[0].tool_call_id == output.tool_calls[0].tool_call_id


def test_collector_completes_on_human_directed_message() -> None:
    collector = EvaluationEventCollector()
    agent = _address("@Manager")
    human = _address("@Human", is_user_proxy=True)
    response = AgentMessage(
        content="The page was ingested.",
        type="notification",
        sender=agent,
        recipient=human,
    )

    collector.on_message(
        SentMessage(
            sender=agent,
            recipient=human,
            message=response,
        )
    )

    output = collector.wait(0)

    assert output.completion_reason == "human_response"
    assert output.final_response == "The page was ingested."
    assert output.human_responses == ["The page was ingested."]
    assert output.messages[0].sender == "@Manager"
    assert output.messages[0].recipient == "@Human"


def test_collector_captures_llm_usage() -> None:
    collector = EvaluationEventCollector()
    agent = _address("@Knowledge")

    collector.on_message(
        EventMessage(
            sender=agent,
            event=LlmUsageEvent(
                run_id="run-1",
                model_name="gpt-test",
                provider_name="openai",
                input_tokens=120,
                output_tokens=30,
                cache_read_tokens=20,
                cache_write_tokens=0,
                requests=1,
            ),
        )
    )

    output = collector.wait(0)

    assert output.llm_usage[0].model_name == "gpt-test"
    assert output.llm_usage[0].input_tokens == 120
    assert output.llm_usage[0].output_tokens == 30
    assert output.llm_usage[0].requests == 1


def test_collector_completes_on_actor_error() -> None:
    collector = EvaluationEventCollector()
    agent = _address("@WebIngest")

    collector.on_message(
        ErrorMessage(
            sender=agent,
            content_type="RuntimeError",
            content="tool failed",
        )
    )

    output = collector.wait(0)

    assert output.completion_reason == "error"
    assert output.errors == ["RuntimeError: tool failed"]


def test_collector_waits_for_multiple_human_responses() -> None:
    collector = EvaluationEventCollector()
    manager = _address("@Manager")
    human = _address("@Human", is_user_proxy=True)

    for content in ("First response", "Second response"):
        collector.on_message(
            SentMessage(
                sender=manager,
                recipient=human,
                message=AgentMessage(
                    content=content,
                    type="notification",
                    sender=manager,
                    recipient=human,
                ),
            )
        )

    output = collector.wait_for_human_responses(2, 0)

    assert output.completion_reason == "human_response"
    assert output.human_responses == ["First response", "Second response"]
    assert output.final_response == "Second response"


def test_repeat_count_must_be_positive() -> None:
    assert positive_int("3") == 3

    with pytest.raises(argparse.ArgumentTypeError, match="value must be at least 1"):
        positive_int("0")


def test_select_case_filters_dataset() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)

    _select_case(dataset, "jettro-unknown-favorite-database")

    assert [case.name for case in dataset.cases] == ["jettro-unknown-favorite-database"]


def test_select_case_rejects_unknown_name() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)

    with pytest.raises(SystemExit, match="Unknown case"):
        _select_case(dataset, "missing-case")
