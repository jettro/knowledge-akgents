"""Tracks URLs submitted for ingestion.

The knowledge graph itself lives in the vector store (in-memory or Qdrant), but nothing
remembered *which* URLs were fed into it. This module adds a tiny, dependency-free cache
of that history as a JSON file under the data directory (see ``settings.urls_file``), so:

- the frontend can show a list of already-imported URLs, and
- starting over is a matter of deleting the data folder (or just ``urls.json``) — this
  file only tracks history, it never influences ingestion or retrieval.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UrlRecord:
    """A single tracked URL and when it was (first/last) submitted for ingestion."""

    url: str
    first_seen_at: str
    last_seen_at: str
    times_submitted: int


class UrlRepository:
    """A small JSON-file-backed store of URLs that have been submitted for ingestion.

    Not a replacement for the knowledge graph — purely a local cache of *inputs*, so the
    application can list what has already been imported and so that history survives
    restarts without needing a database.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def add(self, url: str) -> UrlRecord:
        """Record a URL as (re)submitted for ingestion, creating or bumping its entry."""
        url = url.strip()
        if not url:
            raise ValueError("url must not be empty")

        now = datetime.now(UTC).isoformat()
        with self._lock:
            records = self._read()
            existing = records.get(url)
            if existing is None:
                record = UrlRecord(url=url, first_seen_at=now, last_seen_at=now, times_submitted=1)
            else:
                record = UrlRecord(
                    url=url,
                    first_seen_at=existing["first_seen_at"],
                    last_seen_at=now,
                    times_submitted=int(existing["times_submitted"]) + 1,
                )
            records[url] = asdict(record)
            self._write(records)
            return record

    def list(self) -> list[UrlRecord]:
        """Return tracked URLs, most recently submitted first."""
        with self._lock:
            records = self._read()
        res: list[UrlRecord] = []
        for r in records.values():
            if not isinstance(r, dict) or "url" not in r:
                continue
            url = str(r.get("url", ""))
            if not _is_valid_url(url):
                continue
            res.append(
                UrlRecord(
                    url=url,
                    first_seen_at=str(r.get("first_seen_at", "")),
                    last_seen_at=str(r.get("last_seen_at", "")),
                    times_submitted=int(r.get("times_submitted", 1)),
                )
            )
        return sorted(res, key=lambda r: r.last_seen_at, reverse=True)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s; starting with an empty URL history.", self._path)
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, indent=2, sort_keys=True))
        tmp.replace(self._path)


def _is_valid_url(url: str) -> bool:
    if not url or any(char.isspace() or char in "\"'" for char in url):
        return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname is not None
    except ValueError:
        return False
