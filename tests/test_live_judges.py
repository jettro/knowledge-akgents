"""Tests for live retrieval judge evidence construction."""

from __future__ import annotations

from evals.evaluators.live import build_live_judge_input
from evals.harness.models import TeamCaseInput, TeamCaseOutput, ToolEvidenceRecord


def test_live_judge_uses_only_successful_search_evidence() -> None:
    output = _output(
        [
            ToolEvidenceRecord(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="search-1",
                content="Jettro is a software architect.",
                outcome="success",
            ),
            ToolEvidenceRecord(
                run_id="run-1",
                tool_name="team_activity",
                tool_call_id="team-1",
                content="Internal team state",
                outcome="success",
            ),
            ToolEvidenceRecord(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="search-2",
                content="Failed search content",
                outcome="failed",
            ),
        ]
    )

    judge_input = build_live_judge_input(
        TeamCaseInput(message="What is Jettro's profession?"),
        output,
    )

    assert judge_input is not None
    assert judge_input.question == "What is Jettro's profession?"
    assert judge_input.evidence == "Jettro is a software architect."


def test_live_judge_requires_search_evidence() -> None:
    judge_input = build_live_judge_input(
        TeamCaseInput(message="What is Jettro's profession?"),
        _output([]),
    )

    assert judge_input is None


def _output(evidence: list[ToolEvidenceRecord]) -> TeamCaseOutput:
    return TeamCaseOutput(
        final_response="answer",
        human_responses=["answer"],
        completion_reason="human_response",
        messages=[],
        tool_calls=[],
        tool_returns=[],
        tool_evidence=evidence,
        errors=[],
    )
