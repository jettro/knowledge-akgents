"""Load resolved Knowledge Akgents teams through akgentic-catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from akgentic.agent import AgentConfig
from akgentic.catalog import (
    Catalog,
    CatalogValidationError,
    YamlEntryRepository,
    allowed_prefixes,
    set_allowed_prefixes,
)
from akgentic.core import AgentCard
from akgentic.llm import ModelConfig
from akgentic.team import TeamCard

from knowledge_akgents.change_aware_web import ChangeAwareWebTool
from knowledge_akgents.settings import settings

CATALOG_ROOT = Path(__file__).parents[2] / "config" / "catalog"
PRODUCTION_CATALOG_NAMESPACE = "knowledge-akgents-production"

_extra_prefixes = [prefix for prefix in allowed_prefixes() if prefix != "akgentic."]
if "knowledge_akgents.change_aware_web." not in _extra_prefixes:
    _extra_prefixes.append("knowledge_akgents.change_aware_web.")
set_allowed_prefixes(_extra_prefixes)


def load_team_card(
    namespace: str = PRODUCTION_CATALOG_NAMESPACE,
    *,
    root: Path = CATALOG_ROOT,
    web_repository_path: Path | None = None,
) -> TeamCard:
    """Resolve one catalog namespace and bind environment-specific settings."""
    catalog = Catalog(YamlEntryRepository(root))
    validation = catalog.validate_namespace(namespace)
    if not validation.ok:
        errors = list(validation.global_errors)
        errors.extend(
            f"{issue.entry_id}: {error}"
            for issue in validation.entry_issues
            for error in issue.errors
        )
        raise CatalogValidationError(errors)
    team_card = catalog.load_team(namespace)
    _bind_runtime_configuration(
        team_card,
        web_repository_path=web_repository_path or settings.urls_file,
    )
    return team_card


def load_production_team_card() -> TeamCard:
    """Load the production catalog team for application startup."""
    return load_team_card(PRODUCTION_CATALOG_NAMESPACE)


def load_production_agent_cards() -> dict[str, AgentCard]:
    """Return production cards keyed by configured agent name."""
    team_card = load_production_team_card()
    return team_card.agent_cards


def _bind_runtime_configuration(
    team_card: TeamCard,
    *,
    web_repository_path: Path,
) -> None:
    model = _model()
    for card in team_card.agent_cards.values():
        if not isinstance(card.config, AgentConfig):
            continue
        tools = [
            tool.model_copy(update={"repository_path": web_repository_path})
            if isinstance(tool, ChangeAwareWebTool)
            else tool
            for tool in card.config.tools
        ]
        card.config = card.config.model_copy(
            update={
                "model_cfg": model,
                "tools": tools,
            }
        )


def _model() -> ModelConfig:
    return ModelConfig(
        provider=cast(Any, settings.llm_provider),
        model=settings.llm_model,
    )
