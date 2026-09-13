"""Compatibility helpers backed by the declarative team catalog."""

from __future__ import annotations

from akgentic.agent import AgentConfig
from akgentic.core import AgentCard

from knowledge_akgents.catalog import load_production_agent_cards


def _prompt(card: AgentCard) -> str:
    config = card.config
    if not isinstance(config, AgentConfig) or config.prompt is None:
        raise ValueError(f"Catalog agent {config.name!r} does not define a prompt")
    return config.prompt.template


_DEFAULT_CARDS = load_production_agent_cards()

MANAGER_PROMPT = _prompt(_DEFAULT_CARDS["@Manager"])
KNOWLEDGE_PROMPT = _prompt(_DEFAULT_CARDS["@Knowledge"])
WEBINGEST_PROMPT = _prompt(_DEFAULT_CARDS["@WebIngest"])


def manager_card() -> AgentCard:
    return load_production_agent_cards()["@Manager"]


def knowledge_card() -> AgentCard:
    return load_production_agent_cards()["@Knowledge"]


def webingest_card() -> AgentCard:
    return load_production_agent_cards()["@WebIngest"]


def all_cards() -> list[AgentCard]:
    cards = load_production_agent_cards()
    return [cards["@Manager"], cards["@Knowledge"], cards["@WebIngest"]]
