"""Evaluation-only web tool backed by reviewed local content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from akgentic.tool.core import ToolCard


class FixtureWebTool(ToolCard):
    source_url: str
    content: str

    def get_tools(self) -> list[Callable[..., Any]]:
        source_url = self.source_url
        content = self.content

        def web_fetch_tool(
            urls: list[str],
            query: str,
            chunks_per_source: int = 3,
            timeout: float = 30,
            extract_depth: Literal["basic", "advanced"] = "basic",
        ) -> dict[str, Any]:
            """Extract reviewed fixture content for a known evaluation URL."""
            requested = {url.rstrip("/") for url in urls}
            if source_url.rstrip("/") not in requested:
                return {
                    "results": [],
                    "failed_results": [
                        {
                            "url": url,
                            "error": f"No evaluation fixture is registered for {url}",
                        }
                        for url in urls
                    ],
                }
            return {
                "results": [
                    {
                        "url": source_url,
                        "raw_content": content,
                    }
                ],
                "query": query,
                "chunks_per_source": chunks_per_source,
                "timeout": timeout,
                "extract_depth": extract_depth,
            }

        return [web_fetch_tool]
