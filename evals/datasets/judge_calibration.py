"""Human-labeled cases for calibrating an LLM answer-quality judge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge

GROUNDEDNESS_RUBRIC = """
Judge only whether every factual claim in the candidate answer is supported by
the reviewed evidence in the input.

Fail when the answer invents or contradicts a fact. Do not penalize omissions,
incompleteness, relevance, writing style, or formatting. Treat "Aprico
Consulting" and "Aprico Consultants" as equivalent names.
""".strip()

ANSWER_RELEVANCE_RUBRIC = """
Judge only whether the candidate answer directly and completely answers the
question. Use the reviewed evidence to determine the expected scope and all
required list items.

Fail when the answer is irrelevant or omits a required part of the answer. Do
not judge whether factual claims are supported; a direct but factually incorrect
answer can pass this dimension. Treat "Aprico Consulting" and "Aprico
Consultants" as equivalent names. Do not judge writing style or formatting.
""".strip()


class JudgeCalibrationInput(BaseModel):
    question: str
    evidence: str
    candidate_answer: str


def return_candidate_answer(inputs: JudgeCalibrationInput) -> str:
    return inputs.candidate_answer


def build_judge_calibration_dataset(
    judge_model: str,
) -> Dataset[JudgeCalibrationInput, str, dict[str, Any]]:
    cases = [
        _case(
            "jettro-profession-correct",
            "What is the profession of Jettro Coenradie?",
            "Jettro Coenradie is a software architect and search enthusiast.",
            "Jettro Coenradie is a software architect.",
            human_grounded=True,
            human_relevant=True,
            failure_kind=None,
        ),
        _case(
            "jettro-profession-invented",
            "What is the profession of Jettro Coenradie?",
            "Jettro Coenradie is a software architect and search enthusiast.",
            "Jettro Coenradie is a data scientist.",
            human_grounded=False,
            human_relevant=True,
            failure_kind="invented_fact",
        ),
        _case(
            "jettro-surname-correct",
            "What is the last name of Jettro?",
            "The person's full name is Jettro Coenradie.",
            "Jettro's last name is Coenradie.",
            human_grounded=True,
            human_relevant=True,
            failure_kind=None,
        ),
        _case(
            "jettro-surname-irrelevant",
            "What is the last name of Jettro?",
            "The person's full name is Jettro Coenradie.",
            "Jettro is a software architect.",
            human_grounded=False,
            human_relevant=False,
            failure_kind="irrelevant",
        ),
        _case(
            "yuma-purpose-correct",
            "What does Yuma do?",
            "Yuma is an end-to-end digital transformation partner.",
            "Yuma is an end-to-end digital transformation partner.",
            human_grounded=True,
            human_relevant=True,
            failure_kind=None,
        ),
        _case(
            "yuma-purpose-invented",
            "What does Yuma do?",
            "Yuma is an end-to-end digital transformation partner.",
            "Yuma is a cybersecurity software vendor.",
            human_grounded=False,
            human_relevant=True,
            failure_kind="invented_fact",
        ),
        _case(
            "yuma-companies-correct-name-variant",
            "What companies formed Yuma?",
            (
                "Yuma was formed by xplus, Luminis, BPSOLUTIONS, Total Design, "
                "Aprico Consultants, and B12 Consulting."
            ),
            (
                "Yuma was formed by xplus, Luminis, BPSOLUTIONS, Total Design, "
                "Aprico Consulting, and B12 Consulting."
            ),
            human_grounded=True,
            human_relevant=True,
            failure_kind=None,
        ),
        _case(
            "yuma-companies-incomplete",
            "What companies formed Yuma?",
            (
                "Yuma was formed by xplus, Luminis, BPSOLUTIONS, Total Design, "
                "Aprico Consultants, and B12 Consulting."
            ),
            "Yuma was formed by xplus, Luminis, BPSOLUTIONS, Total Design, and Aprico.",
            human_grounded=True,
            human_relevant=False,
            failure_kind="incomplete_list",
        ),
    ]
    return Dataset(
        name="knowledge-akgents/judge-calibration",
        cases=cases,
        evaluators=[
            LLMJudge(
                rubric=GROUNDEDNESS_RUBRIC,
                model=judge_model,
                include_input=True,
                assertion={
                    "evaluation_name": "groundedness",
                    "include_reason": True,
                },
            ),
            LLMJudge(
                rubric=ANSWER_RELEVANCE_RUBRIC,
                model=judge_model,
                include_input=True,
                assertion={
                    "evaluation_name": "answer_relevance",
                    "include_reason": True,
                },
            ),
        ],
    )


def _case(
    name: str,
    question: str,
    evidence: str,
    candidate_answer: str,
    *,
    human_grounded: bool,
    human_relevant: bool,
    failure_kind: str | None,
) -> Case[JudgeCalibrationInput, str, dict[str, Any]]:
    return Case(
        name=name,
        inputs=JudgeCalibrationInput(
            question=question,
            evidence=evidence,
            candidate_answer=candidate_answer,
        ),
        metadata={
            "human_grounded": human_grounded,
            "human_relevant": human_relevant,
            "failure_kind": failure_kind,
        },
    )
