"""Tests for the fixture-backed knowledge tool."""

from __future__ import annotations

from akgentic.tool.knowledge_graph.models import SearchQuery

from evals.fixture_knowledge import FixtureKnowledgeTool, KnowledgeFixtureRecord


def test_fixture_knowledge_returns_matching_records() -> None:
    tool = FixtureKnowledgeTool(
        records=[
            KnowledgeFixtureRecord(
                name="Jettro Coenradie",
                entity_type="Person",
                description="Jettro Coenradie is a software architect.",
            ),
            KnowledgeFixtureRecord(
                name="Yuma",
                entity_type="Company",
                description="Yuma is a digital transformation partner.",
            ),
        ]
    ).get_tools()[0]

    result = tool(SearchQuery(query="Jettro profession", top_k=10))

    assert "Jettro Coenradie" in result
    assert "software architect" in result
    assert "Yuma" not in result


def test_fixture_knowledge_returns_no_results_for_unknown_query() -> None:
    tool = FixtureKnowledgeTool(
        records=[
            KnowledgeFixtureRecord(
                name="Yuma",
                entity_type="Company",
                description="Yuma is a digital transformation partner.",
            )
        ]
    ).get_tools()[0]

    assert tool(SearchQuery(query="unknown subject")) == "No results found."
