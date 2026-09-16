"""Reusable inputs and agreement reporting for LLM-judge calibration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from pydantic_evals.reporting import EvaluationReport


class JudgeCalibrationInput(BaseModel):
    question: str
    evidence: str
    candidate_answer: str


class AgreementCount(BaseModel):
    agreements: int = 0
    runs: int = 0


class JudgeDecisionComparison(BaseModel):
    human_pass: bool
    judge_pass: bool
    agrees: bool
    reason: str | None = None


class JudgeCaseComparison(BaseModel):
    case: str
    dimensions: dict[str, JudgeDecisionComparison]


class JudgeCalibrationSummary(BaseModel):
    agreement: int
    decision_count: int
    by_dimension: dict[str, AgreementCount]
    by_source_case: dict[str, dict[str, AgreementCount]]
    cases: list[JudgeCaseComparison]


def return_candidate_answer(inputs: JudgeCalibrationInput) -> str:
    return inputs.candidate_answer


def summarize_judge_agreement(
    report: EvaluationReport[Any, Any, Any],
    label_keys: Mapping[str, str],
) -> JudgeCalibrationSummary:
    comparisons: list[JudgeCaseComparison] = []
    by_dimension = {dimension: AgreementCount() for dimension in label_keys}
    grouped: dict[str, dict[str, AgreementCount]] = {}

    for case in report.cases:
        source_name = case.source_case_name or case.name
        group = grouped.setdefault(
            source_name,
            {dimension: AgreementCount() for dimension in label_keys},
        )
        dimensions: dict[str, JudgeDecisionComparison] = {}
        for dimension, label_key in label_keys.items():
            judge_result = case.assertions.get(dimension)
            if judge_result is None:
                raise RuntimeError(
                    f"Missing {dimension} assertion for {case.name}; "
                    f"observed {sorted(case.assertions)}"
                )
            if case.metadata is None or label_key not in case.metadata:
                raise RuntimeError(
                    f"Missing human label {label_key!r} for {case.name}"
                )
            human_pass = bool(case.metadata[label_key])
            judge_pass = bool(judge_result.value)
            agrees = human_pass == judge_pass
            dimensions[dimension] = JudgeDecisionComparison(
                human_pass=human_pass,
                judge_pass=judge_pass,
                agrees=agrees,
                reason=judge_result.reason,
            )
            _record_agreement(by_dimension[dimension], agrees)
            _record_agreement(group[dimension], agrees)
        comparisons.append(
            JudgeCaseComparison(case=case.name, dimensions=dimensions)
        )

    return JudgeCalibrationSummary(
        agreement=sum(
            dimension.agrees
            for comparison in comparisons
            for dimension in comparison.dimensions.values()
        ),
        decision_count=len(comparisons) * len(label_keys),
        by_dimension=by_dimension,
        by_source_case=grouped,
        cases=comparisons,
    )


def _record_agreement(count: AgreementCount, agrees: bool) -> None:
    count.runs += 1
    count.agreements += agrees
