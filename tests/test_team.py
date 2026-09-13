"""Team assembly tests.

These verify the actor wiring (cards, tools, roster) without calling any LLM. Agent
construction requires an API key to be *present* (no network call happens), so a dummy
key is injected before the team boots.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def dummy_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-for-tests")
    monkeypatch.setenv("AKGENTIC_QDRANT_URL", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")


def test_cards_have_expected_tools() -> None:
    from knowledge_akgents.agents import KNOWLEDGE_PROMPT, knowledge_card, webingest_card

    k = knowledge_card()
    w = webingest_card()

    assert k.config.name == "@Knowledge"
    assert w.config.name == "@WebIngest"

    k_tools = {type(t).__name__ for t in k.config.tools}
    w_tools = {type(t).__name__ for t in w.config.tools}

    # Knowledge queries the shared store.
    assert "VectorStoreTool" in k_tools
    assert "KnowledgeGraphTool" in k_tools

    # Web-ingest additionally retrieves web pages.
    assert "VectorStoreTool" in w_tools
    assert "KnowledgeGraphTool" in w_tools
    assert "SearchTool" in w_tools
    assert "never add guessed answer candidates" in KNOWLEDGE_PROMPT
    assert "Please ingest a source via @WebIngest." in KNOWLEDGE_PROMPT


def test_team_boots_with_expected_roster(dummy_openai_key: None) -> None:
    from knowledge_akgents.team import KnowledgeTeam

    events: list[dict] = []
    team = KnowledgeTeam()
    try:
        team.start(publish=events.append)
        roster = team.roster()
    finally:
        team.shutdown()

    assert set(roster) == {"@Manager", "@Knowledge", "@WebIngest"}


def test_send_before_start_raises() -> None:
    from knowledge_akgents.team import KnowledgeTeam

    with pytest.raises(RuntimeError):
        KnowledgeTeam().send("hello")
