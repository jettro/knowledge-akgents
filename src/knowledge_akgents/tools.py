"""Tool cards shared by the team.

Both knowledge-graph cards use the same ``knowledge_graph`` collection, so what the
web-ingest agent writes is exactly what the knowledge agent can query. Each card owns its
storage (akgentic-tool 1.12 removed the separate ``VectorStoreTool`` card): the default
``vector_store=True`` picks the backend the environment provisions, so exporting
``AKGENTIC_QDRANT_URL`` makes the store Qdrant-backed.
"""

from __future__ import annotations

from akgentic.tool.knowledge_graph import KnowledgeGraphTool
from akgentic.tool.search import SearchTool, WebCrawl, WebFetch

from knowledge_akgents.change_aware_web import ChangeAwareWebTool
from knowledge_akgents.settings import settings


def knowledge_query_card() -> KnowledgeGraphTool:
    """Read side: search the knowledge base, no writes."""
    return KnowledgeGraphTool(search=True, update_graph=False)


def knowledge_ingest_card() -> KnowledgeGraphTool:
    """Write side: store extracted entities/relations (and still allow lookups)."""
    return KnowledgeGraphTool(search=True, update_graph=True)


def web_card() -> ChangeAwareWebTool:
    """Retrieve web content and suppress unchanged extracts before graph ingestion."""
    return ChangeAwareWebTool(
        repository_path=settings.urls_file,
        delegate=SearchTool(
            web_search=True,
            web_fetch=WebFetch(timeout=30),
            web_crawl=WebCrawl(timeout=150, max_depth=2, max_breadth=5, limit=10),
        ),
    )
