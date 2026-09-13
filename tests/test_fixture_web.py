"""Tests for the fixed-content evaluation web tool."""

from __future__ import annotations

from pathlib import Path

from evals.catalog import load_case_team_card
from evals.fixture_web import FixtureWebTool


def test_fixture_web_tool_returns_reviewed_content() -> None:
    card = FixtureWebTool(
        source_url="https://coenradie.com/about",
        content="Jettro Coenradie is a software architect.",
    )
    tool = card.get_tools()[0]

    result = tool(
        urls=["https://coenradie.com/about/"],
        query="What is Jettro's profession?",
    )

    assert result["results"][0]["raw_content"] == "Jettro Coenradie is a software architect."
    assert result["query"] == "What is Jettro's profession?"


def test_fixture_web_tool_rejects_unknown_url() -> None:
    card = FixtureWebTool(
        source_url="https://coenradie.com/about",
        content="fixture",
    )
    tool = card.get_tools()[0]

    result = tool(urls=["https://example.com"], query="test")

    assert result["results"] == []
    assert result["failed_results"][0]["url"] == "https://example.com"


def test_fixture_web_tool_returns_configured_failure() -> None:
    card = FixtureWebTool(
        source_url="https://eval.invalid/unreachable",
        failure_message="Connection timed out",
    )
    tool = card.get_tools()[0]

    result = tool(urls=["https://eval.invalid/unreachable"], query="fetch page")

    assert result["results"] == []
    assert result["failed_results"] == [
        {
            "url": "https://eval.invalid/unreachable",
            "error": "Connection timed out",
        }
    ]


def test_fixture_web_tool_returns_sequence_then_repeats_last_content() -> None:
    tool = FixtureWebTool(
        source_url="https://eval.invalid/changed",
        content_sequence=["first", "second"],
    ).get_tools()[0]

    first = tool(urls=["https://eval.invalid/changed"], query="facts")
    second = tool(urls=["https://eval.invalid/changed"], query="facts")
    third = tool(urls=["https://eval.invalid/changed"], query="facts")

    assert first["results"][0]["raw_content"] == "first"
    assert second["results"][0]["raw_content"] == "second"
    assert third["results"][0]["raw_content"] == "second"


def test_evaluation_team_accepts_fixture_tool(tmp_path: Path) -> None:
    fixture = FixtureWebTool(
        source_url="https://coenradie.com/about",
        content="fixture",
    )

    team_card = load_case_team_card("evaluation", tmp_path, web_tool=fixture)
    card = team_card.agent_cards["@WebIngest"]

    assert fixture in card.config.tools
    assert not any(type(tool).__name__ == "ChangeAwareWebTool" for tool in card.config.tools)
