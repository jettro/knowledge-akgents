"""Tests for the initial Jettro ingestion dataset definition."""

from __future__ import annotations

from evals.datasets.jettro_ingestion import build_jettro_ingestion_dataset
from evals.event_evaluators import CalledRequiredTools, ToolCallsSucceeded


def test_jettro_ingestion_requires_only_domain_tools() -> None:
    dataset = build_jettro_ingestion_dataset(timeout_seconds=1)
    tool_evaluator = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, CalledRequiredTools)
    )

    assert tool_evaluator.required_tools == ("web_fetch_tool", "update_graph")
    success_evaluator = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, ToolCallsSucceeded)
    )
    assert success_evaluator.tool_names == ("web_fetch_tool", "update_graph")
