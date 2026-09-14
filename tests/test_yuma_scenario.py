"""Tests for the Yuma multi-turn scenario definition."""

from __future__ import annotations

from evals.scenarios.yuma_scenario import (
    FIXTURE_PATH,
    YUMA_BACKGROUND_URL,
    build_yuma_scenario_dataset,
)
from evals.evaluators.events import (
    CompletedSuccessfully,
    HumanResponseContainsAnyTerm,
    HumanResponseContainsTerms,
    ToolCallCount,
    ToolCallsSucceeded,
)


def test_yuma_scenario_defines_three_ordered_turns() -> None:
    dataset = build_yuma_scenario_dataset(timeout_seconds=1)
    case = dataset.cases[0]

    assert [turn.message for turn in case.inputs.ordered_turns()] == [
        (
            f"Ingest {YUMA_BACKGROUND_URL} and focus on what Yuma does and which "
            "companies formed it."
        ),
        "What does Yuma do?",
        "What companies formed Yuma?",
    ]
    assert case.inputs.fixture_path == str(FIXTURE_PATH)


def test_yuma_scenario_requires_three_responses_and_two_searches() -> None:
    dataset = build_yuma_scenario_dataset(timeout_seconds=1)
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
    success_evaluator = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, ToolCallsSucceeded)
    )

    assert completion.expected_human_responses == 3
    assert search_count.minimum == 2
    assert success_evaluator.tool_names == (
        "web_fetch_tool",
        "update_graph",
        "search_graph",
    )


def test_yuma_company_answer_accepts_aprico_name_variants() -> None:
    dataset = build_yuma_scenario_dataset(timeout_seconds=1)
    company_evaluator = [
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, HumanResponseContainsTerms)
    ][1]

    assert "Aprico" in company_evaluator.required_terms
    assert "Aprico Consultants" not in company_evaluator.required_terms


def test_yuma_description_accepts_current_ai_transformation_wording() -> None:
    dataset = build_yuma_scenario_dataset(timeout_seconds=1)
    description_terms = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, HumanResponseContainsTerms)
        and evaluator.response_index == 1
    )
    transformation_kind = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, HumanResponseContainsAnyTerm)
        and evaluator.response_index == 1
    )

    assert description_terms.required_terms == ("transformation", "partner")
    assert transformation_kind.accepted_terms == (
        "AI transformation",
        "AI-transformation",
        "digital transformation",
    )
