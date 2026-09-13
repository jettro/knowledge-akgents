"""Tests for the human-labeled LLM-judge calibration dataset."""

from __future__ import annotations

from pydantic_evals.evaluators import LLMJudge

from evals.datasets.judge_calibration import (
    ANSWER_RELEVANCE_RUBRIC,
    GROUNDEDNESS_RUBRIC,
    build_judge_calibration_dataset,
    return_candidate_answer,
)


def test_judge_calibration_has_separate_human_labels() -> None:
    dataset = build_judge_calibration_dataset("openai:test-model")

    assert len(dataset.cases) == 8
    invented = dataset.cases[1].metadata
    irrelevant = dataset.cases[3].metadata
    incomplete = dataset.cases[7].metadata
    assert (invented["human_grounded"], invented["human_relevant"]) == (False, True)
    assert (irrelevant["human_grounded"], irrelevant["human_relevant"]) == (False, False)
    assert (incomplete["human_grounded"], incomplete["human_relevant"]) == (True, False)


def test_judge_calibration_covers_targeted_failure_kinds() -> None:
    dataset = build_judge_calibration_dataset("openai:test-model")
    failure_kinds = {
        case.metadata["failure_kind"]
        for case in dataset.cases
        if case.metadata["failure_kind"] is not None
    }

    assert failure_kinds == {"invented_fact", "irrelevant", "incomplete_list"}


def test_judge_uses_input_evidence_and_explicit_rubric() -> None:
    dataset = build_judge_calibration_dataset("openai:test-model")
    judges = [evaluator for evaluator in dataset.evaluators if isinstance(evaluator, LLMJudge)]

    assert len(judges) == 2
    assert all(judge.include_input for judge in judges)
    assert all(not judge.include_expected_output for judge in judges)
    assert all(judge.model == "openai:test-model" for judge in judges)
    assert [judge.assertion["evaluation_name"] for judge in judges] == [
        "groundedness",
        "answer_relevance",
    ]
    assert "Do not penalize omissions" in GROUNDEDNESS_RUBRIC
    assert "direct but factually incorrect" in ANSWER_RELEVANCE_RUBRIC


def test_static_calibration_task_returns_candidate_answer() -> None:
    case = build_judge_calibration_dataset("openai:test-model").cases[0]

    assert return_candidate_answer(case.inputs) == case.inputs.candidate_answer
