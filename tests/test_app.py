"""Input-parsing tests for the websocket message router (no network)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID


def test_parse_plain_text() -> None:
    from knowledge_akgents.app import _parse_input

    assert _parse_input("hello world") == ("hello world", None)


def test_parse_at_routing() -> None:
    from knowledge_akgents.app import _parse_input

    text, target = _parse_input("@Knowledge what do we know about X?")
    assert target == "Knowledge"
    assert text == "what do we know about X?"


def test_parse_json_payload() -> None:
    from knowledge_akgents.app import _parse_input

    text, target = _parse_input('{"text": "ingest it", "target": "WebIngest"}')
    assert text == "ingest it"
    assert target == "WebIngest"


def test_parse_json_without_target() -> None:
    from knowledge_akgents.app import _parse_input

    text, target = _parse_input('{"text": "hi"}')
    assert text == "hi"
    assert target is None


def test_extract_urls_finds_and_dedupes() -> None:
    from knowledge_akgents.app import _extract_urls

    text = "Please ingest https://example.com/page and also https://example.com/page again."
    assert _extract_urls(text) == ["https://example.com/page"]


def test_extract_urls_stops_at_serialized_argument_delimiters() -> None:
    from knowledge_akgents.app import _extract_urls

    text = 'https://coenradie.com/about"],"query":"Extract'
    assert _extract_urls(text) == ["https://coenradie.com/about"]


def test_extract_urls_strips_trailing_punctuation() -> None:
    from knowledge_akgents.app import _extract_urls

    text = "See (https://example.com/a), and https://example.com/b."
    assert _extract_urls(text) == ["https://example.com/a", "https://example.com/b"]


def test_extract_urls_empty_when_no_url() -> None:
    from knowledge_akgents.app import _extract_urls

    assert _extract_urls("no links here") == []


def test_api_urls_endpoint(tmp_path: Any, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from knowledge_akgents import app as app_module
    from knowledge_akgents.repository import UrlRepository

    temp_repo = UrlRepository(tmp_path / "urls.json")
    temp_repo.add("https://test.com/sample")
    fake_team = _FakeManagedTeam(temp_repo)
    monkeypatch.setattr(app_module, "team", fake_team)

    client = TestClient(app_module.app, raise_server_exceptions=False)
    response = client.get("/api/urls")
    assert response.status_code == 200
    data = response.json()
    assert "urls" in data
    assert len(data["urls"]) == 1
    assert data["urls"][0]["url"] == "https://test.com/sample"


def test_system_status_endpoint(monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from knowledge_akgents import app as app_module

    monkeypatch.setattr(
        app_module,
        "storage_status",
        lambda settings, repository, team_id: {
            "mode": "in_memory",
            "persistent": False,
            "qdrant": {"configured": False},
            "imported_urls": {"tracked": 0},
            "synchronization": {"state": "not_verifiable"},
        },
    )
    monkeypatch.setattr(app_module, "team", _FakeManagedTeam())

    client = TestClient(app_module.app, raise_server_exceptions=False)
    response = client.get("/api/system/status")

    assert response.status_code == 200
    data = response.json()
    assert data["storage"]["mode"] == "in_memory"
    assert data["model"]["name"]
    assert "configured" in data["web_search"]


def test_cors_headers_present() -> None:
    from fastapi.testclient import TestClient

    from knowledge_akgents.app import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.options(
        "/api/urls",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:8080")


def test_team_instances_endpoint_marks_active_team(monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from knowledge_akgents import app as app_module

    fake_team = _FakeManagedTeam()
    monkeypatch.setattr(app_module, "team", fake_team)
    client = TestClient(app_module.app, raise_server_exceptions=False)

    response = client.get("/api/team-instances")

    assert response.status_code == 200
    assert response.json()["instances"][0]["active"] is True


def test_activate_team_instance(monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from knowledge_akgents import app as app_module

    fake_team = _FakeManagedTeam()
    monkeypatch.setattr(app_module, "team", fake_team)
    client = TestClient(app_module.app, raise_server_exceptions=False)

    response = client.post(f"/api/team-instances/{fake_team.id}/activate")

    assert response.status_code == 200
    assert response.json()["team_id"] == str(fake_team.id)
    assert fake_team.activated == [fake_team.id]


class _FakeProcess:
    team_id = UUID("00000000-0000-0000-0000-000000000001")
    catalog_namespace = "knowledge-akgents-production"
    team_name = "knowledge-akgents-production"
    team_description = None
    status = type("Status", (), {"value": "running"})()
    created_at = datetime.now(UTC)
    updated_at = created_at


class _FakeManagedTeam:
    def __init__(self, repository: Any = None) -> None:
        if repository is None:
            from knowledge_akgents.repository import UrlRepository

            repository = UrlRepository(Path("/tmp/not-read.json"))
        self.url_repository = repository
        self.id = _FakeProcess.team_id
        self.active_process = _FakeProcess()
        self.activated: list[UUID] = []

    def roster(self) -> list[str]:
        return ["@Manager"]

    def list_instances(self) -> list[_FakeProcess]:
        return [self.active_process]

    def activate(self, team_id: UUID) -> _FakeProcess:
        self.activated.append(team_id)
        return self.active_process
