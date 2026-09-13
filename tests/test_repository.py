"""Tests for the URL-history repository (no network, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path


def test_add_creates_file_and_record(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    record = repo.add(" https://example.com/page ")

    assert record.url == "https://example.com/page"
    assert record.times_submitted == 1
    assert record.first_seen_at == record.last_seen_at
    assert (tmp_path / "urls.json").exists()


def test_add_rejects_empty_url(tmp_path: Path) -> None:
    import pytest

    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    with pytest.raises(ValueError):
        repo.add("   ")


def test_add_dedupes_and_bumps_count(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    first = repo.add("https://example.com")
    second = repo.add("https://example.com")

    assert second.times_submitted == 2
    assert second.first_seen_at == first.first_seen_at
    assert [r.url for r in repo.list()] == ["https://example.com"]


def test_add_preserves_ingestion_metadata(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository, hash_web_content

    repo = UrlRepository(tmp_path / "urls.json")
    repo.add("https://example.com")
    content_hash = hash_web_content("Stored content")
    repo.record_ingested(
        "https://example.com",
        content_hash,
        owned_entities=("Example",),
        owned_relations=(("Example", "Topic", "covers"),),
    )

    submitted_again = repo.add("https://example.com")

    assert submitted_again.times_submitted == 2
    assert submitted_again.content_hash == content_hash
    assert submitted_again.times_ingested == 1
    assert submitted_again.last_status == "ingested"
    assert submitted_again.owned_entities == ("Example",)
    assert submitted_again.owned_relations == (("Example", "Topic", "covers"),)


def test_list_orders_most_recent_first(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    repo.add("https://a.example.com")
    repo.add("https://b.example.com")
    repo.add("https://a.example.com")  # bump a's last_seen_at to the most recent

    urls = [r.url for r in repo.list()]
    assert urls[0] == "https://a.example.com"
    assert set(urls) == {"https://a.example.com", "https://b.example.com"}


def test_history_persists_across_instances(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    path = tmp_path / "urls.json"
    UrlRepository(path).add("https://example.com")

    reloaded = UrlRepository(path).list()
    assert [r.url for r in reloaded] == ["https://example.com"]


def test_list_on_missing_file_is_empty(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "does-not-exist" / "urls.json")
    assert repo.list() == []


def test_hash_normalizes_line_endings_trailing_space_and_blank_lines() -> None:
    from knowledge_akgents.repository import hash_web_content

    first = "Heading\r\n\r\nContent   \r\n"
    second = "Heading\n\n\nContent"

    assert hash_web_content(first) == hash_web_content(second)


def test_check_content_tracks_first_unchanged_and_changed(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    url = "https://example.com/page"
    repo.add(url)

    first = repo.check_content(url, "Version one")
    assert first.decision == "first"
    assert repo.list()[0].content_hash is None

    ingested = repo.record_ingested(url, first.content_hash)
    assert ingested.content_hash == first.content_hash
    assert ingested.times_checked == 1
    assert ingested.times_ingested == 1

    unchanged = repo.check_content(url, "Version one\n")
    assert unchanged.decision == "unchanged"
    assert repo.list()[0].last_status == "unchanged"

    changed = repo.check_content(url, "Version two")
    assert changed.decision == "changed"
    stored = repo.list()[0]
    assert stored.content_hash == first.content_hash
    assert stored.times_checked == 3
    assert stored.times_ingested == 1


def test_failed_check_preserves_successful_metadata(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")
    url = "https://example.com/page"
    repo.add(url)
    first = repo.check_content(url, "Successful content")
    successful = repo.record_ingested(
        url,
        first.content_hash,
        etag='"previous"',
        last_modified="Sat, 13 Sep 2026 10:00:00 GMT",
    )

    failed = repo.record_failed(url, checked=True)

    assert failed.last_status == "failed"
    assert failed.content_hash == successful.content_hash
    assert failed.last_ingested_at == successful.last_ingested_at
    assert failed.etag == successful.etag
    assert failed.last_modified == successful.last_modified
    assert failed.times_checked == 2
    assert failed.times_ingested == 1


def test_replaceable_source_facts_exclude_shared_ownership(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository, hash_web_content

    repo = UrlRepository(tmp_path / "urls.json")
    first_url = "https://example.com/first"
    second_url = "https://example.com/second"
    shared_relation = ("Shared", "Topic", "covers")
    repo.add(first_url)
    repo.record_ingested(
        first_url,
        hash_web_content("first"),
        owned_entities=("First only", "Shared"),
        owned_relations=(("First only", "Shared", "mentions"), shared_relation),
    )
    repo.add(second_url)
    repo.record_ingested(
        second_url,
        hash_web_content("second"),
        owned_entities=("Second only", "Shared"),
        owned_relations=(shared_relation,),
    )

    replaceable = repo.replaceable_source_facts(first_url)

    assert replaceable.entities == ("First only",)
    assert replaceable.relations == (("First only", "Shared", "mentions"),)


def test_content_state_requires_a_submitted_url(tmp_path: Path) -> None:
    import pytest

    from knowledge_akgents.repository import UrlRepository

    repo = UrlRepository(tmp_path / "urls.json")

    with pytest.raises(KeyError, match="has not been submitted"):
        repo.check_content("https://example.com", "content")


def test_list_skips_url_captured_from_serialized_tool_arguments(tmp_path: Path) -> None:
    from knowledge_akgents.repository import UrlRepository

    path = tmp_path / "urls.json"
    valid_url = "https://coenradie.com/about"
    malformed_url = f'{valid_url}"],"query":"Extract'
    path.write_text(
        json.dumps(
            {
                valid_url: {
                    "url": valid_url,
                    "first_seen_at": "2026-09-12T09:35:08+00:00",
                    "last_seen_at": "2026-09-12T09:35:08+00:00",
                    "times_submitted": 1,
                },
                malformed_url: {
                    "url": malformed_url,
                    "first_seen_at": "2026-09-12T09:35:13+00:00",
                    "last_seen_at": "2026-09-12T09:35:13+00:00",
                    "times_submitted": 1,
                },
            }
        )
    )

    records = UrlRepository(path).list()
    assert [record.url for record in records] == [valid_url]
    assert records[0].content_hash is None
    assert records[0].times_checked == 0
    assert records[0].times_ingested == 0
