"""Evaluation-only web tool backed by reviewed local content."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from akgentic.tool.core import ToolCard
from pydantic import Field


class FixtureWebTool(ToolCard):
    source_url: str
    content: str = ""
    content_sequence: list[str] = Field(default_factory=list)
    failure_message: str | None = None

    def get_tools(self) -> list[Callable[..., Any]]:
        source_url = self.source_url
        content = self.content
        content_sequence = self.content_sequence
        failure_message = self.failure_message
        fetch_count = 0

        def web_fetch_tool(
            urls: list[str],
            query: str,
            chunks_per_source: int = 3,
            timeout: float = 30,
            extract_depth: Literal["basic", "advanced"] = "basic",
        ) -> dict[str, Any]:
            """Extract reviewed fixture content for a known evaluation URL."""
            nonlocal fetch_count
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
            if failure_message:
                return {
                    "results": [],
                    "failed_results": [
                        {
                            "url": source_url,
                            "error": failure_message,
                        }
                    ],
                    "query": query,
                }
            selected_content = content
            if content_sequence:
                selected_content = content_sequence[min(fetch_count, len(content_sequence) - 1)]
            fetch_count += 1
            return {
                "results": [
                    {
                        "url": source_url,
                        "raw_content": selected_content,
                    }
                ],
                "query": query,
                "chunks_per_source": chunks_per_source,
                "timeout": timeout,
                "extract_depth": extract_depth,
            }

        return [web_fetch_tool]
