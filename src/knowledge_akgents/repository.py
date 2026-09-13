"""Tracks URL submissions and successful ingestion state.

The knowledge graph itself lives in the vector store (in-memory or Qdrant), but nothing
remembered *which* URLs were fed into it. This module adds a tiny, dependency-free cache
of that state as a JSON file under the data directory (see ``settings.urls_file``), so:

- the frontend can show a list of submitted URLs;
- ingestion can compare fetched content with the last successfully stored version; and
- starting over is a matter of deleting the data folder (or just ``urls.json``) — this
  file never contains the knowledge graph itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

ContentDecision = Literal["first", "unchanged", "changed"]
IngestionStatus = Literal["ingested", "unchanged", "failed"]


@dataclass(frozen=True, slots=True)
class UrlRecord:
    """Submission history plus metadata from the last successful ingestion."""

    url: str
    first_seen_at: str
    last_seen_at: str
    times_submitted: int
    last_checked_at: str | None = None
    last_ingested_at: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    last_status: IngestionStatus | None = None
    times_checked: int = 0
    times_ingested: int = 0
    owned_entities: tuple[str, ...] = ()
    owned_relations: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ContentCheck:
    """Result of comparing fetched content with the last successful ingestion."""

    url: str
    content_hash: str
    decision: ContentDecision


@dataclass(frozen=True, slots=True)
class SourceFacts:
    """Facts that can be removed without deleting ownership from another URL."""

    entities: tuple[str, ...]
    relations: tuple[tuple[str, str, str], ...]


class UrlRepository:
    """A small JSON-file-backed store of URL ingestion metadata.

    Content checks and ingestion commits are intentionally separate. A successful fetch
    can be compared with the stored hash without replacing it; the new hash is committed
    only after the caller confirms that the graph update succeeded.
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
                previous = _record_from_mapping(existing)
                record = UrlRecord(
                    url=url,
                    first_seen_at=previous.first_seen_at,
                    last_seen_at=now,
                    times_submitted=previous.times_submitted + 1,
                    last_checked_at=previous.last_checked_at,
                    last_ingested_at=previous.last_ingested_at,
                    etag=previous.etag,
                    last_modified=previous.last_modified,
                    content_hash=previous.content_hash,
                    last_status=previous.last_status,
                    times_checked=previous.times_checked,
                    times_ingested=previous.times_ingested,
                    owned_entities=previous.owned_entities,
                    owned_relations=previous.owned_relations,
                )
            records[url] = asdict(record)
            self._write(records)
            return record

    def check_content(self, url: str, content: str) -> ContentCheck:
        """Compare fetched content without replacing the last successful hash."""
        content_hash = hash_web_content(content)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            records = self._read()
            previous = self._require_record(records, url)
            if previous.content_hash is None:
                decision: ContentDecision = "first"
            elif previous.content_hash == content_hash:
                decision = "unchanged"
            else:
                decision = "changed"

            updated = _copy_record(
                previous,
                last_checked_at=now,
                last_status="unchanged" if decision == "unchanged" else previous.last_status,
                times_checked=previous.times_checked + 1,
            )
            records[previous.url] = asdict(updated)
            self._write(records)
        return ContentCheck(url=previous.url, content_hash=content_hash, decision=decision)

    def record_ingested(
        self,
        url: str,
        content_hash: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        owned_entities: Iterable[str] | None = None,
        owned_relations: Iterable[tuple[str, str, str]] | None = None,
    ) -> UrlRecord:
        """Commit validator state after the caller confirms a successful graph update."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            records = self._read()
            previous = self._require_record(records, url)
            updated = _copy_record(
                previous,
                last_ingested_at=now,
                etag=etag,
                last_modified=last_modified,
                content_hash=content_hash,
                last_status="ingested",
                times_ingested=previous.times_ingested + 1,
                owned_entities=(
                    _normalize_entity_names(owned_entities)
                    if owned_entities is not None
                    else previous.owned_entities
                ),
                owned_relations=(
                    _normalize_relations(owned_relations)
                    if owned_relations is not None
                    else previous.owned_relations
                ),
            )
            records[previous.url] = asdict(updated)
            self._write(records)
            return updated

    def replaceable_source_facts(self, url: str) -> SourceFacts:
        """Return facts owned by this URL and by no other tracked source."""
        normalized_url = url.strip()
        with self._lock:
            records = [
                _record_from_mapping(raw)
                for raw in self._read().values()
                if isinstance(raw, dict)
            ]
        current = next((record for record in records if record.url == normalized_url), None)
        if current is None:
            raise KeyError(f"URL has not been submitted: {normalized_url}")

        other_entities = {
            entity
            for record in records
            if record.url != normalized_url
            for entity in record.owned_entities
        }
        other_relations = {
            relation
            for record in records
            if record.url != normalized_url
            for relation in record.owned_relations
        }
        return SourceFacts(
            entities=tuple(
                entity for entity in current.owned_entities if entity not in other_entities
            ),
            relations=tuple(
                relation for relation in current.owned_relations if relation not in other_relations
            ),
        )

    def record_failed(self, url: str, *, checked: bool = False) -> UrlRecord:
        """Record a failed fetch or ingestion without replacing successful validators."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            records = self._read()
            previous = self._require_record(records, url)
            updated = _copy_record(
                previous,
                last_checked_at=now if checked else previous.last_checked_at,
                last_status="failed",
                times_checked=previous.times_checked + int(checked),
            )
            records[previous.url] = asdict(updated)
            self._write(records)
            return updated

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
            res.append(_record_from_mapping(r))
        return sorted(res, key=lambda r: r.last_seen_at, reverse=True)

    def get(self, url: str) -> UrlRecord | None:
        """Return one URL record, or ``None`` when it has not been submitted."""
        with self._lock:
            existing = self._read().get(url.strip())
        return _record_from_mapping(existing) if existing is not None else None

    def _require_record(
        self,
        records: dict[str, dict[str, Any]],
        url: str,
    ) -> UrlRecord:
        normalized_url = url.strip()
        existing = records.get(normalized_url)
        if existing is None:
            raise KeyError(f"URL has not been submitted: {normalized_url}")
        return _record_from_mapping(existing)

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


def normalize_web_content(content: str) -> str:
    """Normalize inconsequential line-ending and trailing-whitespace differences."""
    normalized_line_endings = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized_line_endings.split("\n")]
    normalized: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line
        if blank and previous_blank:
            continue
        normalized.append(line)
        previous_blank = blank
    return "\n".join(normalized).strip()


def hash_web_content(content: str) -> str:
    """Return a stable SHA-256 hash for normalized extracted page content."""
    return hashlib.sha256(normalize_web_content(content).encode()).hexdigest()


def _record_from_mapping(data: dict[str, Any]) -> UrlRecord:
    status = data.get("last_status")
    if status not in {"ingested", "unchanged", "failed"}:
        status = None
    return UrlRecord(
        url=str(data.get("url", "")),
        first_seen_at=str(data.get("first_seen_at", "")),
        last_seen_at=str(data.get("last_seen_at", "")),
        times_submitted=int(data.get("times_submitted", 1)),
        last_checked_at=_optional_string(data.get("last_checked_at")),
        last_ingested_at=_optional_string(data.get("last_ingested_at")),
        etag=_optional_string(data.get("etag")),
        last_modified=_optional_string(data.get("last_modified")),
        content_hash=_optional_string(data.get("content_hash")),
        last_status=status,
        times_checked=int(data.get("times_checked", 0)),
        times_ingested=int(data.get("times_ingested", 0)),
        owned_entities=_normalize_entity_names(data.get("owned_entities", [])),
        owned_relations=_normalize_relations(data.get("owned_relations", [])),
    )


def _copy_record(record: UrlRecord, **changes: Any) -> UrlRecord:
    values = asdict(record)
    values.update(changes)
    return UrlRecord(**values)


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _normalize_entity_names(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _normalize_relations(values: Iterable[Any]) -> tuple[tuple[str, str, str], ...]:
    normalized: dict[tuple[str, str, str], None] = {}
    for value in values:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            continue
        relation = tuple(str(part) for part in value)
        if all(relation):
            normalized[(relation[0], relation[1], relation[2])] = None
    return tuple(normalized)


def _is_valid_url(url: str) -> bool:
    if not url or any(char.isspace() or char in "\"'" for char in url):
        return False
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname is not None
    except ValueError:
        return False
