"""Tests for the akgentic-catalog-backed team definition."""

from __future__ import annotations

import pytest
from akgentic.catalog import Catalog, CatalogValidationError, YamlEntryRepository

from evals.catalog import EVALUATION_CATALOG_NAMESPACE, load_case_team_card
from evals.fixture_web import FixtureWebTool
from knowledge_akgents.catalog import (
    CATALOG_ROOT,
    PRODUCTION_CATALOG_NAMESPACE,
    load_team_card,
)


def test_production_namespace_contains_referenced_team_entries() -> None:
    catalog = Catalog(YamlEntryRepository(CATALOG_ROOT))
    entries = catalog.list_by_namespace(PRODUCTION_CATALOG_NAMESPACE)
    team_entry = next(entry for entry in entries if entry.kind == "team")
    meta_entry = next(entry for entry in entries if entry.kind == "meta")

    assert {entry.kind for entry in entries} == {
        "team",
        "agent",
        "prompt",
        "tool",
        "model",
        "meta",
    }
    assert meta_entry.payload["shareable"] is True
    assert team_entry.payload["entry_point"]["card"]["__ref__"] == "human"
    assert [
        member["card"]["__ref__"] for member in team_entry.payload["members"]
    ] == ["manager", "knowledge", "web-ingest"]


def test_production_namespace_loads_native_team_card_and_tools() -> None:
    team_card = load_team_card(PRODUCTION_CATALOG_NAMESPACE)

    assert team_card.name == PRODUCTION_CATALOG_NAMESPACE
    assert team_card.entry_point.card.config.name == "@Human"
    assert (
        team_card.entry_point.card.agent_class
        == "knowledge_akgents.trace_context.TraceContextHumanProxy"
    )
    assert [member.card.config.name for member in team_card.members] == [
        "@Manager",
        "@Knowledge",
        "@WebIngest",
    ]
    knowledge = team_card.agent_cards["@Knowledge"]
    web_ingest = team_card.agent_cards["@WebIngest"]
    assert knowledge.agent_class == "knowledge_akgents.trace_context.TraceContextBaseAgent"
    assert web_ingest.agent_class == "knowledge_akgents.trace_context.TraceContextBaseAgent"
    assert [type(tool).__name__ for tool in knowledge.config.tools] == [
        "VectorStoreTool",
        "KnowledgeGraphTool",
    ]
    assert [type(tool).__name__ for tool in web_ingest.config.tools] == [
        "VectorStoreTool",
        "ChangeAwareWebTool",
        "KnowledgeGraphTool",
    ]


def test_evaluation_namespace_references_production_agents() -> None:
    catalog = Catalog(YamlEntryRepository(CATALOG_ROOT))
    entries = catalog.list_by_namespace(EVALUATION_CATALOG_NAMESPACE)
    team_entry = next(entry for entry in entries if entry.kind == "team")

    assert {entry.kind for entry in entries} == {"team", "meta"}
    assert team_entry.payload["entry_point"]["card"]["__namespace__"] == (
        PRODUCTION_CATALOG_NAMESPACE
    )
    assert {
        member["card"]["__namespace__"] for member in team_entry.payload["members"]
    } == {PRODUCTION_CATALOG_NAMESPACE}

    team_card = load_team_card(EVALUATION_CATALOG_NAMESPACE)

    assert team_card.name == EVALUATION_CATALOG_NAMESPACE
    assert sorted(team_card.agent_cards) == [
        "@Human",
        "@Knowledge",
        "@Manager",
        "@WebIngest",
    ]


def test_evaluation_composition_replaces_web_tool_outside_src(tmp_path) -> None:
    fixture = FixtureWebTool(
        source_url="https://eval.invalid/page",
        content="fixture",
    )

    team_card = load_case_team_card(
        "evaluation",
        tmp_path,
        web_tool=fixture,
    )

    web_ingest = team_card.agent_cards["@WebIngest"]
    assert fixture in web_ingest.config.tools
    assert not any(type(tool).__name__ == "ChangeAwareWebTool" for tool in web_ingest.config.tools)


def test_production_composition_rejects_fixture_tools(tmp_path) -> None:
    fixture = FixtureWebTool(
        source_url="https://eval.invalid/page",
        content="fixture",
    )

    with pytest.raises(ValueError, match="cannot use fixture tools"):
        load_case_team_card("production", tmp_path, web_tool=fixture)


def test_catalog_rejects_unknown_namespace() -> None:
    with pytest.raises(CatalogValidationError):
        load_team_card("missing")


def test_catalog_package_rejects_unknown_team_fields(tmp_path) -> None:
    team_dir = tmp_path / PRODUCTION_CATALOG_NAMESPACE / "team"
    team_dir.mkdir(parents=True)
    (team_dir / "invalid.yaml").write_text(
        f"""
id: invalid
kind: team
namespace: {PRODUCTION_CATALOG_NAMESPACE}
user_id: anonymous
model_type: akgentic.team.models.TeamCard
description: Invalid.
payload:
  name: invalid
  unexpected: true
  entry_point:
    card:
      agent_class: akgentic.agent.HumanProxy
      description: Human.
      config:
        name: "@Human"
        role: Human
  members: []
""",
        encoding="utf-8",
    )

    with pytest.raises(CatalogValidationError, match="unexpected"):
        load_team_card(root=tmp_path)
