"""Evaluation-owned catalog selection and fixture composition."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from akgentic.agent import AgentConfig
from akgentic.team import TeamCard
from akgentic.tool.core import ToolCard
from akgentic.tool.knowledge_graph import KnowledgeGraphTool

from knowledge_akgents.catalog import (
    PRODUCTION_CATALOG_NAMESPACE,
    load_team_card,
)
from knowledge_akgents.change_aware_web import ChangeAwareWebTool

EVALUATION_CATALOG_NAMESPACE = "knowledge-akgents-evaluation"
TeamCatalog = Literal["evaluation", "production"]


def load_case_team_card(
    catalog_team: TeamCatalog,
    state_dir: Path,
    *,
    web_tool: ToolCard | None = None,
    knowledge_tool: ToolCard | None = None,
) -> TeamCard:
    """Load the selected team and apply case fixtures only to the evaluation team."""
    if catalog_team not in {"evaluation", "production"}:
        raise ValueError(f"Unknown catalog team: {catalog_team!r}")
    namespace = (
        EVALUATION_CATALOG_NAMESPACE
        if catalog_team == "evaluation"
        else PRODUCTION_CATALOG_NAMESPACE
    )
    team_card = load_team_card(
        namespace,
        web_repository_path=state_dir / "urls.json",
    )
    if catalog_team == "production":
        if web_tool is not None or knowledge_tool is not None:
            raise ValueError(
                "The production catalog team cannot use fixture tools; "
                "use the evaluation catalog team for deterministic fixtures."
            )
        return team_card

    if web_tool is not None:
        _replace_agent_tool(
            team_card,
            agent_name="@WebIngest",
            replacement=web_tool,
            expected_type=ChangeAwareWebTool,
        )
    if knowledge_tool is not None:
        _replace_agent_tool(
            team_card,
            agent_name="@Knowledge",
            replacement=knowledge_tool,
            expected_type=KnowledgeGraphTool,
            require_read_only=True,
        )
    return team_card


def _replace_agent_tool(
    team_card: TeamCard,
    *,
    agent_name: str,
    replacement: ToolCard,
    expected_type: type[ToolCard],
    require_read_only: bool = False,
) -> None:
    card = team_card.agent_cards[agent_name]
    if not isinstance(card.config, AgentConfig):
        raise ValueError(f"Catalog agent {agent_name!r} does not use AgentConfig")

    replacements = 0
    tools: list[ToolCard] = []
    for tool in card.config.tools:
        matches = isinstance(tool, expected_type)
        if require_read_only and isinstance(tool, KnowledgeGraphTool):
            matches = matches and not tool.update_graph
        if matches:
            tools.append(replacement)
            replacements += 1
        else:
            tools.append(tool)

    if replacements != 1:
        raise ValueError(
            f"Expected exactly one replaceable {expected_type.__name__} "
            f"on {agent_name}, found {replacements}"
        )
    card.config = card.config.model_copy(update={"tools": tools})
