"""Tests for routing evaluation cases."""

from __future__ import annotations

from evals.scenarios.routing import build_routing_dataset
from evals.evaluators.events import DidNotInvolveActors, FollowedMessageRoute


def test_routing_dataset_defines_direct_and_manager_cases() -> None:
    dataset = build_routing_dataset(timeout_seconds=1)

    assert [case.name for case in dataset.cases] == [
        "direct-knowledge-bypasses-manager",
        "direct-web-ingest-bypasses-manager",
        "read-only-question-with-url-routes-to-knowledge",
    ]
    assert [case.inputs.target for case in dataset.cases] == [
        "@Knowledge",
        "@WebIngest",
        None,
    ]


def test_direct_routing_cases_exclude_other_team_members() -> None:
    dataset = build_routing_dataset(timeout_seconds=1)
    direct_knowledge, direct_web, read_only_url = dataset.cases

    knowledge_exclusion = next(
        evaluator
        for evaluator in direct_knowledge.evaluators
        if isinstance(evaluator, DidNotInvolveActors)
    )
    web_exclusion = next(
        evaluator
        for evaluator in direct_web.evaluators
        if isinstance(evaluator, DidNotInvolveActors)
    )
    read_only_route = next(
        evaluator
        for evaluator in read_only_url.evaluators
        if isinstance(evaluator, FollowedMessageRoute)
    )

    assert knowledge_exclusion.actor_names == ("@Manager", "@WebIngest")
    assert web_exclusion.actor_names == ("@Manager", "@Knowledge")
    assert ("@Manager", "@Knowledge") in read_only_route.expected_route
