"""Tests for the fixed-content evaluation web tool."""

from __future__ import annotations

from evals.fixture_web import FixtureWebTool
from knowledge_akgents.agents import webingest_card


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


def test_webingest_card_accepts_fixture_tool() -> None:
    fixture = FixtureWebTool(
        source_url="https://coenradie.com/about",
        content="fixture",
    )

    card = webingest_card(fixture)

    assert fixture in card.config.tools
    assert not any(type(tool).__name__ == "SearchTool" for tool in card.config.tools)
