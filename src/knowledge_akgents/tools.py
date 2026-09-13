"""Tool cards shared by the team.

All knowledge-base tools point at the same ``#VectorStore`` singleton and the same
``knowledge_graph`` collection, so what the web-ingest agent writes is exactly what the
knowledge agent can query. Exporting ``AKGENTIC_QDRANT_URL`` makes that store Qdrant-backed.
"""

from __future__ import annotations

from akgentic.tool.knowledge_graph import KnowledgeGraphTool
from akgentic.tool.search import SearchTool, WebCrawl, WebFetch
from akgentic.tool.vector_store import VectorStoreTool

from knowledge_akgents.change_aware_web import ChangeAwareWebTool
from knowledge_akgents.settings import settings


def vector_store_card() -> VectorStoreTool:
    """The config card that guarantees the shared ``#VectorStore`` actor exists."""
    return VectorStoreTool()


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
