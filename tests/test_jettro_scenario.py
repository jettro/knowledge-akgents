"""Tests for the Jettro multi-turn scenario definition."""

from __future__ import annotations

from evals.datasets.jettro_scenario import build_jettro_scenario_dataset
from evals.evaluators.events import CompletedSuccessfully, ToolCallCount, ToolCallsSucceeded


def test_jettro_scenario_defines_three_ordered_turns() -> None:
    dataset = build_jettro_scenario_dataset(timeout_seconds=1)
    case = dataset.cases[0]

    assert [turn.message for turn in case.inputs.ordered_turns()] == [
        "Ingest https://coenradie.com/about and focus on Jettro Coenradie's profession and name.",
        "What is the profession of Jettro Coenradie?",
        "What is the last name of Jettro?",
    ]


def test_jettro_scenario_requires_three_responses_and_two_searches() -> None:
    dataset = build_jettro_scenario_dataset(timeout_seconds=1)
    completion = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, CompletedSuccessfully)
    )
    search_count = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, ToolCallCount) and evaluator.tool_name == "search_graph"
    )

    assert completion.expected_human_responses == 3
    assert search_count.minimum == 2
    success_evaluator = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, ToolCallsSucceeded)
    )
    assert success_evaluator.tool_names == (
        "web_fetch_tool",
        "update_graph",
        "search_graph",
    )
