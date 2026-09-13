"""Tests for the retrieval-only pilot dataset."""

from __future__ import annotations

from evals.datasets.retrieval_only import FIXTURE_PATH, build_retrieval_only_dataset
from evals.event_evaluators import (
    DidNotCallTools,
    HumanResponseContainsTerms,
    ToolCallCount,
)


def test_retrieval_only_dataset_defines_canonical_and_paraphrased_cases() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)

    assert [case.name for case in dataset.cases] == [
        "jettro-profession",
        "jettro-profession-paraphrase",
        "jettro-surname",
        "jettro-surname-paraphrase",
        "yuma-purpose",
        "yuma-purpose-paraphrase",
        "yuma-companies",
        "yuma-companies-paraphrase",
        "jettro-unknown-favorite-database",
    ]
    assert all(case.inputs.knowledge_fixture_path == str(FIXTURE_PATH) for case in dataset.cases)
    assert all(len(case.inputs.ordered_turns()) == 1 for case in dataset.cases)
    assert [case.metadata["prompt_variant"] for case in dataset.cases] == [
        "canonical",
        "paraphrase",
        "canonical",
        "paraphrase",
        "canonical",
        "paraphrase",
        "canonical",
        "paraphrase",
        "negative-control",
    ]


def test_retrieval_only_cases_define_answer_specific_evaluators() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)

    required_terms = [
        evaluator.required_terms
        for case in dataset.cases
        for evaluator in case.evaluators
        if isinstance(evaluator, HumanResponseContainsTerms)
    ]
    forbidden = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, DidNotCallTools)
    )

    assert required_terms == [
        ("software architect",),
        ("software architect",),
        ("Coenradie",),
        ("Coenradie",),
        ("digital", "transformation", "partner"),
        ("digital", "transformation", "partner"),
        ("xplus", "Luminis", "BPSOLUTIONS", "Total Design", "Aprico", "B12 Consulting"),
        ("xplus", "Luminis", "BPSOLUTIONS", "Total Design", "Aprico", "B12 Consulting"),
        ("ingest",),
    ]
    assert forbidden.forbidden_tools == ("web_fetch_tool", "update_graph")


def test_unknown_knowledge_case_limits_search_retries() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)
    case = next(case for case in dataset.cases if case.name == "jettro-unknown-favorite-database")
    search_limit = next(
        evaluator for evaluator in case.evaluators if isinstance(evaluator, ToolCallCount)
    )

    assert search_limit.minimum == 1
    assert search_limit.maximum == 2
