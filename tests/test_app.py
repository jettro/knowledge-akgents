"""Input-parsing tests for the websocket message router (no network)."""

from __future__ import annotations


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
