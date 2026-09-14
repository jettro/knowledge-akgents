"""Tests for the human-labeled LLM-judge calibration dataset."""

from __future__ import annotations

from pydantic_evals.evaluators import LLMJudge

from evals.scenarios.judge_calibration import (
    ANSWER_RELEVANCE_RUBRIC,
    GROUNDEDNESS_RUBRIC,
    build_judge_calibration_dataset,
    return_candidate_answer,
)


def test_judge_calibration_has_separate_human_labels() -> None:
    dataset = build_judge_calibration_dataset("openai:test-model")
    cases = {case.name: case.metadata for case in dataset.cases}

    assert len(dataset.cases) == 11
    invented = cases["jettro-profession-invented"]
    irrelevant = cases["jettro-surname-irrelevant"]
    incomplete = cases["yuma-companies-incomplete"]
    unavailable = cases["jettro-favorite-database-unavailable"]
    hallucinated = cases["jettro-favorite-database-hallucinated"]
    refusal = cases["jettro-favorite-database-generic-refusal"]
    assert (invented["human_grounded"], invented["human_relevant"]) == (False, True)
    assert (irrelevant["human_grounded"], irrelevant["human_relevant"]) == (False, False)
    assert (incomplete["human_grounded"], incomplete["human_relevant"]) == (True, False)
    assert (unavailable["human_grounded"], unavailable["human_relevant"]) == (True, True)
    assert (hallucinated["human_grounded"], hallucinated["human_relevant"]) == (
        False,
        True,
    )
    assert (refusal["human_grounded"], refusal["human_relevant"]) == (True, False)


def test_judge_calibration_covers_targeted_failure_kinds() -> None:
    dataset = build_judge_calibration_dataset("openai:test-model")
    failure_kinds = {
        case.metadata["failure_kind"]
        for case in dataset.cases
        if case.metadata["failure_kind"] is not None
    }

    assert failure_kinds == {
        "invented_fact",
        "irrelevant",
        "incomplete_list",
        "unhelpful_missing_fact",
    }


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
    assert "operational next-step suggestions" in GROUNDEDNESS_RUBRIC
    assert "direct but factually incorrect" in ANSWER_RELEVANCE_RUBRIC
    assert "does not contain the requested fact" in ANSWER_RELEVANCE_RUBRIC
    assert "groundedness judges factual support separately" in ANSWER_RELEVANCE_RUBRIC


def test_static_calibration_task_returns_candidate_answer() -> None:
    case = build_judge_calibration_dataset("openai:test-model").cases[0]

    assert return_candidate_answer(case.inputs) == case.inputs.candidate_answer
