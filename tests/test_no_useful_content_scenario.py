"""Tests for the boilerplate-only ingestion scenario."""

from __future__ import annotations

from evals.datasets.no_useful_content_scenario import (
    FIXTURE_PATH,
    NO_USEFUL_CONTENT_URL,
    build_no_useful_content_scenario_dataset,
)
from evals.event_evaluators import HumanResponseContainsAnyTerm, ToolCallCount


def test_no_useful_content_scenario_uses_isolated_fixture() -> None:
    dataset = build_no_useful_content_scenario_dataset(timeout_seconds=1)
    case = dataset.cases[0]

    assert case.name == "skip-graph-update-for-boilerplate-only-page"
    assert case.inputs.fixture_source_url == NO_USEFUL_CONTENT_URL
    assert case.inputs.fixture_path == str(FIXTURE_PATH)
    assert case.metadata["fixture_kind"] == "synthetic-boilerplate-only"


def test_no_useful_content_scenario_forbids_graph_update() -> None:
    dataset = build_no_useful_content_scenario_dataset(timeout_seconds=1)
    update_limit = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, ToolCallCount) and evaluator.tool_name == "update_graph"
    )

    assert update_limit.minimum == 0
    assert update_limit.maximum == 0


def test_no_useful_content_scenario_accepts_usable_wording() -> None:
    dataset = build_no_useful_content_scenario_dataset(timeout_seconds=1)
    response_evaluator = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, HumanResponseContainsAnyTerm)
    )

    assert "no usable" in response_evaluator.accepted_terms
