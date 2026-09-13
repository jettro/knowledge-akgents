"""Evaluation-only knowledge search backed by reviewed local records."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from akgentic.tool.core import ToolCard
from akgentic.tool.knowledge_graph.models import SearchQuery
from pydantic import BaseModel

_STOP_WORDS = {
    "a",
    "an",
    "does",
    "do",
    "is",
    "of",
    "the",
    "what",
    "which",
}


class KnowledgeFixtureRecord(BaseModel):
    name: str
    entity_type: str
    description: str


class KnowledgeFixture(BaseModel):
    records: list[KnowledgeFixtureRecord]


class FixtureKnowledgeTool(ToolCard):
    records: list[KnowledgeFixtureRecord]

    def get_tools(self) -> list[Callable[..., Any]]:
        records = self.records

        def search_graph(query: SearchQuery) -> str:
            """Search the reviewed evaluation knowledge fixture."""
            query_terms = _search_terms(query.query)
            ranked = sorted(
                (
                    (
                        len(query_terms & _search_terms(f"{record.name} {record.description}")),
                        index,
                        record,
                    )
                    for index, record in enumerate(records)
                ),
                key=lambda item: (-item[0], item[1]),
            )
            matches = [item for item in ranked if item[0] > 0]
            limit = query.top_k or 10
            if not matches:
                return "No results found."

            lines = ["Search Results:"]
            for overlap, _, record in matches[:limit]:
                lines.append(
                    f"  - [entity] {record.name} ({record.entity_type}): "
                    f"{record.description} (score: {overlap / len(query_terms):.2f})"
                )
            return "\n".join(lines)

        return [search_graph]


def _search_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", value.casefold()) if term not in _STOP_WORDS}
