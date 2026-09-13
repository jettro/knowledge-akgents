"""Deterministic tests for hash-based web ingestion decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from akgentic.tool.search import SearchTool

from knowledge_akgents.change_aware_web import (
    ChangeAwareWebTool,
    ContentChangeTracker,
    SourceRelation,
)
from knowledge_akgents.repository import UrlRepository


def _fetch_result(url: str, content: str) -> dict[str, object]:
    return {
        "results": [{"url": url, "raw_content": content}],
        "failed_results": [],
        "request_id": "fixture-request",
    }


class StubSearchTool(SearchTool):
    def get_tools(self) -> list[Any]:
        def web_fetch_tool(
            urls: list[str],
            query: str,
            chunks_per_source: int = 3,
            timeout: float = 30,
            extract_depth: str = "basic",
        ) -> dict[str, object]:
            del query, chunks_per_source, timeout, extract_depth
            return _fetch_result(urls[0], "Fixture content")

        return [web_fetch_tool]


def test_tool_card_exposes_fetch_and_guarded_completion_tools(tmp_path: Path) -> None:
    card = ChangeAwareWebTool(
        repository_path=tmp_path / "urls.json",
        delegate=StubSearchTool(web_search=False, web_crawl=False, web_fetch=True),
    )
    tools = {tool.__name__: tool for tool in card.get_tools()}

    assert set(tools) == {
        "web_fetch_tool",
        "commit_web_ingestion",
        "fail_web_ingestion",
    }

    fetched = tools["web_fetch_tool"](
        urls=["https://example.com/page"],
        query="fixture",
    )
    candidate = fetched["results"][0]
    committed = tools["commit_web_ingestion"](
        url=candidate["url"],
        content_hash=candidate["content_hash"],
        owned_entities=["Fixture"],
        owned_relations=[],
    )
    assert committed["status"] == "ingested"


def test_first_fetch_requires_explicit_commit(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    result = tracker.process_fetch_result([url], _fetch_result(url, "Version one"), force=False)

    fetched = result["results"][0]
    assert fetched["content_status"] == "first"
    assert repository.get(url).content_hash is None

    committed = tracker.commit(
        url,
        fetched["content_hash"],
        owned_entities=["Version one"],
        owned_relations=[],
    )
    assert committed["status"] == "ingested"
    assert repository.get(url).content_hash == fetched["content_hash"]


def test_unchanged_fetch_omits_raw_content_and_graph_candidate(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    first = tracker.process_fetch_result([url], _fetch_result(url, "Same content"), force=False)
    tracker.commit(
        url,
        first["results"][0]["content_hash"],
        owned_entities=["Same content"],
        owned_relations=[],
    )
    unchanged = tracker.process_fetch_result(
        [url],
        _fetch_result(url, "Same content\n"),
        force=False,
    )

    assert unchanged["results"] == []
    assert unchanged["unchanged_results"][0]["status"] == "unchanged"
    assert "raw_content" not in unchanged["unchanged_results"][0]

    with pytest.raises(ValueError, match="No pending"):
        tracker.commit(url, unchanged["unchanged_results"][0]["content_hash"])


def test_force_exposes_unchanged_content_for_reingestion(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    first = tracker.process_fetch_result([url], _fetch_result(url, "Same content"), force=False)
    tracker.commit(
        url,
        first["results"][0]["content_hash"],
        owned_entities=["Same content"],
        owned_relations=[],
    )
    forced = tracker.process_fetch_result([url], _fetch_result(url, "Same content"), force=True)

    assert forced["results"][0]["content_status"] == "forced"
    tracker.commit(
        url,
        forced["results"][0]["content_hash"],
        owned_entities=["Same content"],
        owned_relations=[],
    )
    assert repository.get(url).times_ingested == 2


def test_changed_fetch_keeps_old_hash_until_commit(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    first = tracker.process_fetch_result([url], _fetch_result(url, "Version one"), force=False)
    first_hash = first["results"][0]["content_hash"]
    tracker.commit(
        url,
        first_hash,
        owned_entities=["Version one", "Stale entity"],
        owned_relations=[
            SourceRelation(
                from_entity="Version one",
                to_entity="Stale entity",
                relation_type="mentions",
            )
        ],
    )

    changed = tracker.process_fetch_result([url], _fetch_result(url, "Version two"), force=False)
    changed_hash = changed["results"][0]["content_hash"]

    assert changed["results"][0]["content_status"] == "changed"
    assert changed_hash != first_hash
    assert repository.get(url).content_hash == first_hash
    assert changed["results"][0]["previous_source_facts"] == {
        "entities": ["Version one", "Stale entity"],
        "relations": [
            {
                "from_entity": "Version one",
                "to_entity": "Stale entity",
                "relation_type": "mentions",
            }
        ],
    }

    tracker.commit(
        url,
        changed_hash,
        owned_entities=["Version two"],
        owned_relations=[],
    )
    assert repository.get(url).content_hash == changed_hash
    assert repository.get(url).owned_entities == ("Version two",)


def test_failed_fetch_preserves_last_successful_hash(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    first = tracker.process_fetch_result([url], _fetch_result(url, "Stored content"), force=False)
    first_hash = first["results"][0]["content_hash"]
    tracker.commit(
        url,
        first_hash,
        owned_entities=["Stored content"],
        owned_relations=[],
    )

    failure = {
        "results": [],
        "failed_results": [{"url": url, "error": "timed out"}],
    }
    returned = tracker.process_fetch_result([url], failure, force=False)

    assert returned == failure
    record = repository.get(url)
    assert record.last_status == "failed"
    assert record.content_hash == first_hash
    assert record.times_ingested == 1


def test_graph_failure_discards_candidate_without_committing_hash(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    result = tracker.process_fetch_result([url], _fetch_result(url, "Candidate"), force=False)
    content_hash = result["results"][0]["content_hash"]
    failed = tracker.fail(url, content_hash)

    assert failed == {"url": url, "status": "failed"}
    assert repository.get(url).content_hash is None

    with pytest.raises(ValueError, match="No pending"):
        tracker.commit(url, content_hash)


def test_commit_rejects_a_hash_not_returned_by_fetch(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    tracker = ContentChangeTracker(repository)
    url = "https://example.com/page"

    tracker.process_fetch_result([url], _fetch_result(url, "Candidate"), force=False)

    with pytest.raises(ValueError, match="does not match"):
        tracker.commit(url, "not-the-returned-hash")
