"""Storage diagnostics tests without a real Qdrant server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge_akgents.repository import UrlRepository, hash_web_content
from knowledge_akgents.settings import Settings
from knowledge_akgents.storage_status import CollectionStatus, storage_status


def test_in_memory_status_is_not_verifiable(tmp_path: Path) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    repository.add("https://example.com")

    result = storage_status(
        Settings(akgentic_qdrant_url="", _env_file=None),
        repository,
    )

    assert result["mode"] == "in_memory"
    assert result["persistent"] is False
    assert result["qdrant"]["reachable"] is None
    assert result["imported_urls"]["tracked"] == 1
    assert result["synchronization"]["state"] == "not_verifiable"


def test_qdrant_status_redacts_credentials_and_reports_connection_failure(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repository = UrlRepository(tmp_path / "urls.json")

    def fail(*args: object) -> CollectionStatus:
        raise OSError("connection refused")

    monkeypatch.setattr(
        "knowledge_akgents.storage_status._get_collection_status",
        fail,
    )
    result = storage_status(
        Settings(
            akgentic_qdrant_url="https://user:secret@qdrant.example:6333/root?token=secret",
            _env_file=None,
        ),
        repository,
    )

    assert result["qdrant"]["target"] == "https://qdrant.example:6333/root"
    assert result["qdrant"]["reachable"] is False
    assert result["synchronization"]["state"] == "unknown"


def test_missing_collection_conflicts_with_ingested_url_history(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    url = "https://example.com"
    repository.add(url)
    repository.record_ingested(url, hash_web_content("stored"))
    monkeypatch.setattr(
        "knowledge_akgents.storage_status._get_collection_status",
        lambda *args: CollectionStatus(name="knowledge_graph", exists=False),
    )

    result = storage_status(
        Settings(akgentic_qdrant_url="http://qdrant:6333", _env_file=None),
        repository,
    )

    assert result["imported_urls"]["successfully_ingested"] == 1
    assert result["synchronization"]["state"] == "out_of_sync"


def test_nonempty_qdrant_and_ingested_urls_are_plausibly_synchronized(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    repository = UrlRepository(tmp_path / "urls.json")
    url = "https://example.com"
    repository.add(url)
    repository.record_ingested(url, hash_web_content("stored"))
    monkeypatch.setattr(
        "knowledge_akgents.storage_status._get_collection_status",
        lambda *args: CollectionStatus(
            name="knowledge_graph",
            exists=True,
            status="green",
            points_count=12,
            indexed_vectors_count=12,
        ),
    )

    result = storage_status(
        Settings(akgentic_qdrant_url="http://qdrant:6333", _env_file=None),
        repository,
    )

    assert result["qdrant"]["reachable"] is True
    assert result["qdrant"]["collection"]["points_count"] == 12
    assert result["synchronization"]["state"] == "plausible"
