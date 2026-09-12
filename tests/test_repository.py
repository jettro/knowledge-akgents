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

    assert [record.url for record in UrlRepository(path).list()] == [valid_url]
