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

Judge factual claims about the subject of the user's question. Do not require
retrieved knowledge evidence to support operational next-step suggestions,
such as asking for a source to ingest, or attribution that a team member
recommended that next step.
""".strip()

ANSWER_RELEVANCE_RUBRIC = """
Judge only whether the candidate answer directly and completely answers the
question. Use the reviewed evidence to determine the expected scope and all
required list items.

Fail when the answer is irrelevant or omits a required part of the answer. Do
not judge whether factual claims are supported; a direct but factually incorrect
answer can pass this dimension. Treat "Aprico Consulting" and "Aprico
Consultants" as equivalent names. Do not judge writing style or formatting.

When the reviewed evidence does not contain the requested fact, a complete and
relevant answer may clearly state that the evidence does not provide it. A
generic refusal that does not connect the missing answer to the reviewed
evidence is incomplete. However, if the candidate directly supplies the
requested fact, judge that answer as relevant even when the fact is unsupported;
groundedness judges factual support separately.
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
        _case(
            "jettro-favorite-database-unavailable",
            "What is Jettro Coenradie's favorite database?",
            "Jettro Coenradie is a software architect and search enthusiast.",
            (
                "The reviewed evidence does not state Jettro Coenradie's favorite "
                "database. @Knowledge recommends ingesting a relevant source via "
                "@WebIngest."
            ),
            human_grounded=True,
            human_relevant=True,
            failure_kind=None,
        ),
        _case(
            "jettro-favorite-database-hallucinated",
            "What is Jettro Coenradie's favorite database?",
            "Jettro Coenradie is a software architect and search enthusiast.",
            "Jettro Coenradie's favorite database is Elasticsearch.",
            human_grounded=False,
            human_relevant=True,
            failure_kind="invented_fact",
        ),
        _case(
            "jettro-favorite-database-generic-refusal",
            "What is Jettro Coenradie's favorite database?",
            "Jettro Coenradie is a software architect and search enthusiast.",
            "I don't know.",
            human_grounded=True,
            human_relevant=False,
            failure_kind="unhelpful_missing_fact",
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
