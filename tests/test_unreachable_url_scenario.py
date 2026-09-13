"""Tests for the controlled unreachable-URL scenario."""

from __future__ import annotations

from evals.datasets.unreachable_url_scenario import (
    FAILURE_MESSAGE,
    UNREACHABLE_URL,
    build_unreachable_url_scenario_dataset,
)
from evals.evaluators.events import ToolCallCount, ToolEvidenceContainsTerms


def test_unreachable_url_scenario_configures_fixture_failure() -> None:
    dataset = build_unreachable_url_scenario_dataset(timeout_seconds=1)
    case = dataset.cases[0]

    assert case.name == "report-web-fetch-failure-without-graph-update"
    assert case.inputs.fixture_source_url == UNREACHABLE_URL
    assert case.inputs.fixture_path is None
    assert case.inputs.fixture_web_failure == FAILURE_MESSAGE
    assert case.metadata["fixture_kind"] == "synthetic-web-failure"


def test_unreachable_url_scenario_requires_failure_evidence_and_no_update() -> None:
    dataset = build_unreachable_url_scenario_dataset(timeout_seconds=1)
    evidence = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, ToolEvidenceContainsTerms)
    )
    update_limit = next(
        evaluator
        for evaluator in dataset.evaluators
        if isinstance(evaluator, ToolCallCount) and evaluator.tool_name == "update_graph"
    )

    assert evidence.tool_name == "web_fetch_tool"
    assert evidence.required_terms == ("failed_results", FAILURE_MESSAGE)
    assert update_limit.maximum == 0
