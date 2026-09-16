"""Tests for live retrieval judge evidence construction."""

from __future__ import annotations

from akgentic_evals.calibration import (
    EvidenceJudgeInput,
    build_tool_evidence_judge_input,
)
from akgentic_evals.models import (
    AkgenticCaseOutput,
    ToolEvidenceRecord,
    ToolReturnRecord,
)
from akgentic_evals.runtime import AkgenticCaseInput


def test_live_judge_uses_only_successful_search_evidence() -> None:
    output = _output(
        evidence=[
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
        ],
        returns=[
            ToolReturnRecord(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="search-1",
                success=True,
            ),
            ToolReturnRecord(
                run_id="run-1",
                tool_name="team_activity",
                tool_call_id="team-1",
                success=True,
            ),
            ToolReturnRecord(
                run_id="run-1",
                tool_name="search_graph",
                tool_call_id="search-2",
                success=False,
            ),
        ],
    )

    judge_input = build_tool_evidence_judge_input(
        AkgenticCaseInput(message="What is Jettro's profession?"),
        output,
        tool_name="search_graph",
    )

    assert judge_input is not None
    assert isinstance(judge_input, EvidenceJudgeInput)
    assert judge_input.question == "What is Jettro's profession?"
    assert judge_input.evidence == "Jettro is a software architect."


def test_live_judge_requires_search_evidence() -> None:
    judge_input = build_tool_evidence_judge_input(
        AkgenticCaseInput(message="What is Jettro's profession?"),
        _output(evidence=[]),
        tool_name="search_graph",
    )

    assert judge_input is None


def _output(
    evidence: list[ToolEvidenceRecord],
    returns: list[ToolReturnRecord] | None = None,
) -> AkgenticCaseOutput:
    return AkgenticCaseOutput(
        final_response="answer",
        human_responses=["answer"],
        completion_reason="human_response",
        messages=[],
        tool_calls=[],
        tool_returns=returns or [],
        tool_evidence=evidence,
        errors=[],
    )
