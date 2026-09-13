"""Tests for the retrieval-only pilot dataset."""

from __future__ import annotations

from evals.datasets.retrieval_only import (
    FIXTURE_PATH,
    MISSING_KNOWLEDGE_TERMS,
    build_retrieval_only_dataset,
)
from evals.event_evaluators import (
    DidNotCallTools,
    HumanResponseContainsAnyTerm,
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
        "jettro-profession-and-yuma-purpose",
        "yuma-consulting-founders",
        "jettro-unknown-favorite-database",
        "jettro-profession-and-unknown-favorite-database",
    ]
    assert all(case.inputs.knowledge_fixture_path == str(FIXTURE_PATH) for case in dataset.cases)
    assert all(len(case.inputs.ordered_turns()) == 1 for case in dataset.cases)
    assert {case.name: case.metadata["prompt_variant"] for case in dataset.cases} == {
        "jettro-profession": "canonical",
        "jettro-profession-paraphrase": "paraphrase",
        "jettro-surname": "canonical",
        "jettro-surname-paraphrase": "paraphrase",
        "yuma-purpose": "canonical",
        "yuma-purpose-paraphrase": "paraphrase",
        "yuma-companies": "canonical",
        "yuma-companies-paraphrase": "paraphrase",
        "jettro-profession-and-yuma-purpose": "multi-entity",
        "yuma-consulting-founders": "filtered-list",
        "jettro-unknown-favorite-database": "negative-control",
        "jettro-profession-and-unknown-favorite-database": (
            "partial-knowledge-negative-control"
        ),
    }


def test_retrieval_only_cases_define_answer_specific_evaluators() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)

    required_terms = {
        case.name: [
            evaluator.required_terms
            for evaluator in case.evaluators
            if isinstance(evaluator, HumanResponseContainsTerms)
        ]
        for case in dataset.cases
    }
    forbidden = next(
        evaluator for evaluator in dataset.evaluators if isinstance(evaluator, DidNotCallTools)
    )

    assert required_terms["jettro-profession"] == [("software architect",)]
    assert required_terms["jettro-profession-and-yuma-purpose"] == [
        ("software architect", "digital", "transformation", "partner")
    ]
    assert required_terms["yuma-consulting-founders"] == [
        ("Aprico", "B12 Consulting")
    ]
    assert required_terms["jettro-unknown-favorite-database"] == [("ingest",)]
    assert required_terms["jettro-profession-and-unknown-favorite-database"] == [
        ("software architect", "ingest")
    ]
    assert forbidden.forbidden_tools == ("web_fetch_tool", "update_graph")


def test_negative_control_cases_limit_search_retries() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)
    expected_limits = {
        "jettro-unknown-favorite-database": 2,
        "jettro-profession-and-unknown-favorite-database": 3,
    }

    for case_name, maximum in expected_limits.items():
        case = next(case for case in dataset.cases if case.name == case_name)
        search_limit = next(
            evaluator for evaluator in case.evaluators if isinstance(evaluator, ToolCallCount)
        )
        assert search_limit.minimum == 1
        assert search_limit.maximum == maximum


def test_negative_control_cases_share_missing_knowledge_vocabulary() -> None:
    dataset = build_retrieval_only_dataset(timeout_seconds=1)
    negative_cases = [
        case for case in dataset.cases if "negative-control" in case.metadata["prompt_variant"]
    ]

    assert "not present" in MISSING_KNOWLEDGE_TERMS
    for case in negative_cases:
        evaluator = next(
            evaluator
            for evaluator in case.evaluators
            if isinstance(evaluator, HumanResponseContainsAnyTerm)
        )
        assert evaluator.accepted_terms == MISSING_KNOWLEDGE_TERMS
