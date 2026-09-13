"""Change-aware wrapper for Akgentic's Tavily-backed web tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from akgentic.tool.core import ToolCard
from pydantic import BaseModel, SerializeAsAny

from knowledge_akgents.repository import UrlRepository


class SourceRelation(BaseModel):
    """A relation triple owned by one ingested source."""

    from_entity: str
    to_entity: str
    relation_type: str


class ContentChangeTracker:
    """Coordinate fetch decisions with explicit post-ingestion commits."""

    def __init__(self, repository: UrlRepository) -> None:
        self._repository = repository
        self._pending: dict[str, str] = {}

    def process_fetch_result(
        self,
        urls: list[str],
        result: Any,
        *,
        force: bool,
    ) -> Any:
        """Annotate changed content and omit unchanged content unless forced."""
        for url in urls:
            self._ensure_submitted(url)

        if not isinstance(result, Mapping):
            for url in urls:
                self._repository.record_failed(url, checked=True)
            return result

        processed = dict(result)
        fetched_results: list[dict[str, Any]] = []
        unchanged_results: list[dict[str, str]] = []

        for raw_result in result.get("results", []):
            if not isinstance(raw_result, Mapping):
                continue
            item = dict(raw_result)
            url = str(item.get("url", "")).strip()
            content = item.get("raw_content")
            if not url or not isinstance(content, str):
                fetched_results.append(item)
                continue

            self._ensure_submitted(url)
            check = self._repository.check_content(url, content)
            if check.decision == "unchanged" and not force:
                unchanged_results.append(
                    {
                        "url": url,
                        "content_hash": check.content_hash,
                        "status": "unchanged",
                    }
                )
                continue

            item["content_hash"] = check.content_hash
            item["content_status"] = "forced" if force else check.decision
            if check.decision == "changed" and not force:
                previous = self._repository.replaceable_source_facts(url)
                item["previous_source_facts"] = {
                    "entities": list(previous.entities),
                    "relations": [
                        {
                            "from_entity": relation[0],
                            "to_entity": relation[1],
                            "relation_type": relation[2],
                        }
                        for relation in previous.relations
                    ],
                }
            self._pending[url] = check.content_hash
            fetched_results.append(item)

        for failed_result in result.get("failed_results", []):
            if not isinstance(failed_result, Mapping):
                continue
            failed_url = str(failed_result.get("url", "")).strip()
            if failed_url:
                self._ensure_submitted(failed_url)
                self._repository.record_failed(failed_url, checked=True)

        processed["results"] = fetched_results
        if unchanged_results:
            processed["unchanged_results"] = unchanged_results
        return processed

    def commit(
        self,
        url: str,
        content_hash: str,
        owned_entities: list[str] | None = None,
        owned_relations: list[SourceRelation] | None = None,
    ) -> dict[str, Any]:
        """Persist a candidate hash after a successful graph update."""
        normalized_url = url.strip()
        expected_hash = self._pending.get(normalized_url)
        if expected_hash is None:
            raise ValueError(f"No pending fetched content for {normalized_url}")
        if content_hash != expected_hash:
            raise ValueError("Content hash does not match the pending fetched content")

        relation_tuples = (
            [
                (relation.from_entity, relation.to_entity, relation.relation_type)
                for relation in owned_relations
            ]
            if owned_relations is not None
            else None
        )
        record = self._repository.record_ingested(
            normalized_url,
            content_hash,
            owned_entities=owned_entities,
            owned_relations=relation_tuples,
        )
        del self._pending[normalized_url]
        return {
            "url": record.url,
            "content_hash": record.content_hash,
            "status": record.last_status,
            "times_ingested": record.times_ingested,
        }

    def fail(self, url: str, content_hash: str) -> dict[str, str]:
        """Discard a pending candidate after a failed graph update."""
        normalized_url = url.strip()
        expected_hash = self._pending.get(normalized_url)
        if expected_hash is None:
            raise ValueError(f"No pending fetched content for {normalized_url}")
        if content_hash != expected_hash:
            raise ValueError("Content hash does not match the pending fetched content")

        self._repository.record_failed(normalized_url)
        del self._pending[normalized_url]
        return {"url": normalized_url, "status": "failed"}

    def _ensure_submitted(self, url: str) -> None:
        if self._repository.get(url) is None:
            self._repository.add(url)


class ChangeAwareWebTool(ToolCard):
    """Wrap a web ToolCard so unchanged extracts can skip graph ingestion."""

    repository_path: Path
    delegate: SerializeAsAny[ToolCard]

    def get_tools(self) -> list[Callable[..., Any]]:
        delegate_tools = self.delegate.get_tools()
        original_fetch = next(
            (tool for tool in delegate_tools if tool.__name__ == "web_fetch_tool"),
            None,
        )
        if original_fetch is None:
            raise ValueError("ChangeAwareWebTool requires a web_fetch_tool")

        tracker = ContentChangeTracker(UrlRepository(self.repository_path))

        def web_fetch_tool(
            urls: list[str],
            query: str,
            chunks_per_source: int = 3,
            timeout: float = 30,
            extract_depth: Literal["basic", "advanced"] = "basic",
            force: bool = False,
        ) -> Any:
            """Fetch pages and return only new or changed extracted content.

            Set force only when the user explicitly requests reprocessing. Results
            include a content hash that must be committed after update_graph succeeds.
            An unchanged page is returned under unchanged_results without raw content.
            """
            result = original_fetch(
                urls=urls,
                query=query,
                chunks_per_source=chunks_per_source,
                timeout=timeout,
                extract_depth=extract_depth,
            )
            return tracker.process_fetch_result(urls, result, force=force)

        def commit_web_ingestion(
            url: str,
            content_hash: str,
            owned_entities: list[str] | None = None,
            owned_relations: list[SourceRelation] | None = None,
        ) -> dict[str, Any]:
            """Commit the content hash and current source-owned facts after update_graph."""
            return tracker.commit(url, content_hash, owned_entities, owned_relations)

        def fail_web_ingestion(url: str, content_hash: str) -> dict[str, str]:
            """Discard a fetched content candidate after update_graph fails."""
            return tracker.fail(url, content_hash)

        return [
            *(tool for tool in delegate_tools if tool is not original_fetch),
            web_fetch_tool,
            commit_web_ingestion,
            fail_web_ingestion,
        ]
