"""Operational status for Qdrant and imported-URL tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from knowledge_akgents.repository import UrlRepository
from knowledge_akgents.settings import Settings

KNOWLEDGE_GRAPH_COLLECTION = "knowledge_graph"


@dataclass(frozen=True, slots=True)
class CollectionStatus:
    name: str
    exists: bool
    status: str | None = None
    points_count: int | None = None
    indexed_vectors_count: int | None = None


def storage_status(settings: Settings, repository: UrlRepository) -> dict[str, Any]:
    """Return sanitized storage configuration, connectivity, and consistency hints."""
    records = repository.list()
    tracked_urls = len(records)
    ingested_urls = sum(record.content_hash is not None for record in records)
    failed_urls = sum(record.last_status == "failed" for record in records)

    if not settings.qdrant_enabled:
        return {
            "mode": "in_memory",
            "persistent": False,
            "qdrant": {
                "configured": False,
                "target": None,
                "reachable": None,
                "error": None,
                "collection": None,
            },
            "imported_urls": {
                "tracked": tracked_urls,
                "successfully_ingested": ingested_urls,
                "failed": failed_urls,
            },
            "synchronization": {
                "state": "not_verifiable",
                "reason": (
                    "The in-memory graph cannot be inspected outside the running "
                    "actor process."
                ),
            },
        }

    target = _sanitized_url(settings.akgentic_qdrant_url)
    try:
        collection = _get_collection_status(
            settings.akgentic_qdrant_url,
            settings.akgentic_qdrant_api_key,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "mode": "qdrant",
            "persistent": True,
            "qdrant": {
                "configured": True,
                "target": target,
                "reachable": False,
                "error": str(exc),
                "collection": None,
            },
            "imported_urls": {
                "tracked": tracked_urls,
                "successfully_ingested": ingested_urls,
                "failed": failed_urls,
            },
            "synchronization": {
                "state": "unknown",
                "reason": "Qdrant could not be inspected.",
            },
        }

    synchronization = _synchronization_status(ingested_urls, collection)
    return {
        "mode": "qdrant",
        "persistent": True,
        "qdrant": {
            "configured": True,
            "target": target,
            "reachable": True,
            "error": None,
            "collection": asdict(collection),
        },
        "imported_urls": {
            "tracked": tracked_urls,
            "successfully_ingested": ingested_urls,
            "failed": failed_urls,
        },
        "synchronization": synchronization,
    }


def _get_collection_status(url: str, api_key: str) -> CollectionStatus:
    endpoint = f"{url.rstrip('/')}/collections/{KNOWLEDGE_GRAPH_COLLECTION}"
    headers = {"api-key": api_key} if api_key else {}
    request = Request(endpoint, headers=headers)
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
    except HTTPError as exc:
        if exc.code == 404:
            return CollectionStatus(name=KNOWLEDGE_GRAPH_COLLECTION, exists=False)
        raise OSError(f"Qdrant returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise OSError(f"Could not connect to Qdrant: {exc.reason}") from exc

    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("Qdrant collection response did not contain a result object")
    return CollectionStatus(
        name=KNOWLEDGE_GRAPH_COLLECTION,
        exists=True,
        status=_optional_string(result.get("status")),
        points_count=_optional_int(result.get("points_count")),
        indexed_vectors_count=_optional_int(result.get("indexed_vectors_count")),
    )


def _synchronization_status(
    ingested_urls: int,
    collection: CollectionStatus,
) -> dict[str, str]:
    points = collection.points_count or 0
    if not collection.exists or points == 0:
        if ingested_urls:
            return {
                "state": "out_of_sync",
                "reason": (
                    "Imported URLs claim successful ingestion, but the Qdrant "
                    "knowledge_graph collection is empty or missing."
                ),
            }
        return {
            "state": "empty",
            "reason": "Neither imported URLs nor Qdrant graph points are present.",
        }
    if not ingested_urls:
        return {
            "state": "out_of_sync",
            "reason": (
                "Qdrant contains graph points, but no imported URL has a successful "
                "ingestion record."
            ),
        }
    return {
        "state": "plausible",
        "reason": (
            "Both imported URL records and Qdrant graph points exist. Counts cannot "
            "be compared directly because one URL can create many graph points."
        ),
    }


def _sanitized_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path.rstrip("/"), "", ""))


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None
