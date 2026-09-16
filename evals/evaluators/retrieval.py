"""Opt-in LLM judges for actual retrieval-case answers and evidence."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    EvaluatorOutput,
)
from pydantic_evals.evaluators.llm_as_a_judge import judge_input_output

from akgentic_evals.calibration import build_tool_evidence_judge_input
from akgentic_evals.models import AkgenticCaseOutput
from akgentic_evals.runtime import AkgenticCaseInput
from evals.scenarios.judge_calibration import (
    ANSWER_RELEVANCE_RUBRIC,
    GROUNDEDNESS_RUBRIC,
)


@dataclass
class RetrievalAnswerJudges(
    Evaluator[AkgenticCaseInput, AkgenticCaseOutput, dict[str, object]]
):
    model: str

    async def evaluate(
        self,
        ctx: EvaluatorContext[
            AkgenticCaseInput,
            AkgenticCaseOutput,
            dict[str, object],
        ],
    ) -> EvaluatorOutput:
        judge_input = build_tool_evidence_judge_input(
            ctx.inputs,
            ctx.output,
            tool_name="search_graph",
        )
        if judge_input is None:
            reason = "No successful search_graph evidence was captured"
            return {
                "groundedness": EvaluationReason(value=False, reason=reason),
                "answer_relevance": EvaluationReason(value=False, reason=reason),
            }

        answer = ctx.output.final_response or ""
        groundedness = await judge_input_output(
            judge_input,
            answer,
            GROUNDEDNESS_RUBRIC,
            self.model,
        )
        relevance = await judge_input_output(
            judge_input,
            answer,
            ANSWER_RELEVANCE_RUBRIC,
            self.model,
        )
        return {
            "groundedness": EvaluationReason(
                value=groundedness.pass_,
                reason=groundedness.reason,
            ),
            "answer_relevance": EvaluationReason(
                value=relevance.pass_,
                reason=relevance.reason,
            ),
        }
