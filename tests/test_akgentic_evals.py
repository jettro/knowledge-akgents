"""Tests for reusable Akgentic evaluation primitives."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from akgentic_evals.collector import EvaluationEventCollector
from akgentic_evals.completion import MessageResponseCompletion
from akgentic_evals.evaluators import LlmUsageWithinLimits
from akgentic_evals.events import (
    MessageObserved,
    ToolCalled,
    ToolEvidenceObserved,
    ToolReturned,
    UsageObserved,
)
from akgentic_evals.runtime import (
    AkgenticCaseInput,
    ConversationTurn,
    run_case,
    run_case_with_factory,
)


def test_collector_builds_correlated_successful_tool_invocation() -> None:
    collector = EvaluationEventCollector()
    collector.on_event(
        ToolCalled(
            run_id="run-1",
            tool_name="search_graph",
            tool_call_id="call-1",
            arguments_raw='{"query": "Jettro"}',
            arguments={"query": "Jettro"},
        )
    )
    collector.on_event(
        ToolReturned(
            run_id="run-1",
            tool_name="search_graph",
            tool_call_id="call-1",
            success=True,
        )
    )
    collector.on_event(
        ToolEvidenceObserved(
            run_id="run-1",
            tool_name="search_graph",
            tool_call_id="call-1",
            content="Jettro is a software architect.",
            outcome="success",
        )
    )
    collector.on_event(
        MessageObserved(
            sender="@Manager",
            recipient="@Human",
            message_type="AgentMessage",
            content="Jettro is a software architect.",
        )
    )

    output = collector.wait_for_responses(1, 0)
    invocations = output.tool_invocations(tool_name="search_graph", successful=True)

    assert output.final_response == "Jettro is a software architect."
    assert len(invocations) == 1
    assert invocations[0].id.run_id == "run-1"
    assert [record.content for record in invocations[0].evidence] == [
        "Jettro is a software architect."
    ]


def test_same_tool_call_id_in_another_run_does_not_correlate() -> None:
    collector = EvaluationEventCollector()
    collector.on_event(
        ToolCalled(
            run_id="run-2",
            tool_name="search_graph",
            tool_call_id="call-1",
            arguments_raw="{}",
            arguments={},
        )
    )
    collector.on_event(
        ToolReturned(
            run_id="run-1",
            tool_name="search_graph",
            tool_call_id="call-1",
            success=True,
        )
    )

    output = collector.wait_for_responses(0, 0)

    assert output.tool_invocations(tool_name="search_graph", successful=True)[0].call is None


def test_run_case_drives_turns_and_always_shuts_down_runtime() -> None:
    runtime = FakeRuntime()

    output = run_case(
        AkgenticCaseInput(
            turns=[
                ConversationTurn(message="first"),
                ConversationTurn(message="second", target="@Researcher"),
            ],
            timeout_seconds=1,
        ),
        runtime,
    )

    assert output.human_responses == ["first", "second"]
    assert runtime.turns[1].target == "@Researcher"
    assert runtime.shutdown_called


def test_case_input_normalizes_a_single_message_to_one_turn() -> None:
    inputs = AkgenticCaseInput(
        message="Ask the specialist",
        target="@Knowledge",
        timeout_seconds=1,
    )

    assert inputs.ordered_turns() == [
        ConversationTurn(message="Ask the specialist", target="@Knowledge")
    ]


def test_case_input_requires_exactly_one_conversation_form() -> None:
    with pytest.raises(ValueError, match="Provide either message or turns"):
        AkgenticCaseInput(timeout_seconds=1)

    with pytest.raises(ValueError, match="Provide either message or turns"):
        AkgenticCaseInput(
            message="duplicate",
            turns=[ConversationTurn(message="duplicate")],
            timeout_seconds=1,
        )


def test_runtime_factory_receives_application_owned_case_input() -> None:
    inputs = AkgenticCaseInput(message="factory case", timeout_seconds=1)
    factory = FakeRuntimeFactory()

    output = run_case_with_factory(inputs, factory)

    assert factory.inputs is inputs
    assert output.final_response == "factory case"


def test_completion_policy_can_select_a_specific_response_sender() -> None:
    collector = EvaluationEventCollector(
        completion_policy=MessageResponseCompletion(sender="@Manager")
    )
    collector.on_event(
        MessageObserved(
            sender="@Researcher",
            recipient="@Human",
            message_type="AgentMessage",
            content="intermediate",
        )
    )
    collector.on_event(
        MessageObserved(
            sender="@Manager",
            recipient="@Human",
            message_type="AgentMessage",
            content="final",
        )
    )

    output = collector.wait_for_responses(1, 0)

    assert output.human_responses == ["final"]


def test_run_case_shuts_down_runtime_when_start_fails() -> None:
    runtime = FakeRuntime(start_error=RuntimeError("start failed"))

    with pytest.raises(RuntimeError, match="start failed"):
        run_case(
            AkgenticCaseInput(
                turns=[ConversationTurn(message="never sent")],
                timeout_seconds=1,
            ),
            runtime,
        )

    assert runtime.shutdown_called


def test_usage_evaluator_aggregates_normalized_usage_records() -> None:
    collector = EvaluationEventCollector()
    collector.on_event(
        UsageObserved(
            run_id="run-1",
            model_name="model",
            provider_name="provider",
            input_tokens=80,
            output_tokens=20,
            cache_read_tokens=0,
            cache_write_tokens=0,
            requests=1,
        )
    )
    output = collector.wait_for_responses(0, 0)

    result = LlmUsageWithinLimits(
        max_input_tokens=100,
        max_output_tokens=25,
        max_requests=1,
    ).evaluate(type("Context", (), {"output": output})())

    assert result.value


class FakeRuntime:
    def __init__(self, start_error: Exception | None = None) -> None:
        self.event_handler = None
        self.turns: list[ConversationTurn] = []
        self.shutdown_called = False
        self.start_error = start_error

    def start(self, event_handler) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.event_handler = event_handler

    def send(self, turn: ConversationTurn) -> None:
        assert self.event_handler is not None
        self.turns.append(turn)
        self.event_handler(
            MessageObserved(
                sender="@Manager",
                recipient="@Human",
                message_type="AgentMessage",
                content=turn.message,
            )
        )

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeRuntimeFactory:
    def __init__(self) -> None:
        self.inputs: AkgenticCaseInput | None = None

    @contextmanager
    def runtime(self, inputs: AkgenticCaseInput) -> Iterator[FakeRuntime]:
        self.inputs = inputs
        yield FakeRuntime()
