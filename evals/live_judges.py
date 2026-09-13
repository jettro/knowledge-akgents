"""Opt-in LLM judges for actual retrieval-case answers and evidence."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel
from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    EvaluatorOutput,
)
from pydantic_evals.evaluators.llm_as_a_judge import judge_input_output

from evals.datasets.judge_calibration import (
    ANSWER_RELEVANCE_RUBRIC,
    GROUNDEDNESS_RUBRIC,
)
from evals.models import TeamCaseInput, TeamCaseOutput


class LiveJudgeInput(BaseModel):
    question: str
    evidence: str


@dataclass
class LiveRetrievalJudges(Evaluator[TeamCaseInput, TeamCaseOutput, dict[str, object]]):
    model: str

    async def evaluate(
        self,
        ctx: EvaluatorContext[
            TeamCaseInput,
            TeamCaseOutput,
            dict[str, object],
        ],
    ) -> EvaluatorOutput:
        judge_input = build_live_judge_input(ctx.inputs, ctx.output)
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


def build_live_judge_input(
    inputs: TeamCaseInput,
    output: TeamCaseOutput,
) -> LiveJudgeInput | None:
    evidence = [
        record.content
        for record in output.tool_evidence
        if record.tool_name == "search_graph" and record.outcome == "success"
    ]
    if not evidence:
        return None
    return LiveJudgeInput(
        question=inputs.ordered_turns()[-1].message,
        evidence="\n\n".join(evidence),
    )
