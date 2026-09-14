"""Drive the already-running Knowledge Akgents application for one eval case."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from websockets.sync.client import connect

from evals.harness.models import (
    LlmUsageRecord,
    MessageRecord,
    TeamCaseInput,
    TeamCaseOutput,
    ToolCallRecord,
    ToolEvidenceRecord,
    ToolReturnRecord,
)


def require_running_system(system_url: str) -> None:
    """Fail fast unless the configured Knowledge Akgents backend is reachable."""
    endpoint = f"{system_url.rstrip('/')}/api/status"
    try:
        with urlopen(endpoint, timeout=5) as response:
            payload = json.loads(response.read())
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not reach the running Knowledge Akgents system at {endpoint}: {exc}"
        ) from exc
    if payload.get("service") != "knowledge-akgents":
        raise ValueError(f"{endpoint} is not a Knowledge Akgents backend")


def run_running_system_case(
    inputs: TeamCaseInput,
    *,
    system_url: str,
) -> TeamCaseOutput:
    """Execute a case through the running backend's public WebSocket boundary."""
    messages: list[MessageRecord] = []
    tool_calls: list[ToolCallRecord] = []
    tool_returns: list[ToolReturnRecord] = []
    tool_evidence: list[ToolEvidenceRecord] = []
    llm_usage: list[LlmUsageRecord] = []
    errors: list[str] = []
    human_responses: list[str] = []
    completion_reason = "timeout"

    try:
        with connect(_websocket_url(system_url), open_timeout=5) as websocket:
            websocket.recv(timeout=5)  # initial connection/roster event
            for expected_count, turn in enumerate(inputs.ordered_turns(), start=1):
                websocket.send(
                    json.dumps({"text": turn.message, "target": turn.target})
                    if turn.target
                    else turn.message
                )
                deadline = time.monotonic() + inputs.timeout_seconds
                while len(human_responses) < expected_count and not errors:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    raw = websocket.recv(timeout=remaining)
                    data = json.loads(raw)
                    _record_event(
                        data,
                        messages=messages,
                        tool_calls=tool_calls,
                        tool_returns=tool_returns,
                        tool_evidence=tool_evidence,
                        llm_usage=llm_usage,
                        errors=errors,
                        human_responses=human_responses,
                    )
                if errors or len(human_responses) < expected_count:
                    break
            if len(human_responses) == len(inputs.ordered_turns()):
                completion_reason = "human_response"
            elif errors:
                completion_reason = "error"
    except TimeoutError:
        completion_reason = "timeout"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        completion_reason = "error"

    return TeamCaseOutput(
        final_response=human_responses[-1] if human_responses else None,
        human_responses=human_responses,
        completion_reason=completion_reason,
        messages=messages,
        tool_calls=tool_calls,
        tool_returns=tool_returns,
        tool_evidence=tool_evidence,
        llm_usage=llm_usage,
        errors=errors,
    )


def _record_event(
    data: dict[str, Any],
    *,
    messages: list[MessageRecord],
    tool_calls: list[ToolCallRecord],
    tool_returns: list[ToolReturnRecord],
    tool_evidence: list[ToolEvidenceRecord],
    llm_usage: list[LlmUsageRecord],
    errors: list[str],
    human_responses: list[str],
) -> None:
    kind = data.get("kind")
    if kind == "message":
        record = MessageRecord(
            sender=data.get("sender"),
            recipient=data.get("recipient"),
            message_type=str(data.get("type", "")),
            content=str(data.get("content", "")),
        )
        messages.append(record)
        if (
            record.recipient == "@Human"
            and record.sender != "@Human"
            and record.content
        ):
            human_responses.append(record.content)
    elif kind == "tool_call":
        arguments_raw = str(data.get("arguments", ""))
        try:
            arguments = json.loads(arguments_raw)
            parse_error = None
        except json.JSONDecodeError as exc:
            arguments = None
            parse_error = str(exc)
        tool_calls.append(
            ToolCallRecord(
                run_id=str(data.get("run_id", "")),
                tool_name=str(data.get("tool", "")),
                tool_call_id=str(data.get("tool_call_id", "")),
                arguments_raw=arguments_raw,
                arguments=arguments,
                parse_error=parse_error,
            )
        )
    elif kind == "tool_return":
        tool_returns.append(
            ToolReturnRecord(
                run_id=str(data.get("run_id", "")),
                tool_name=str(data.get("tool", "")),
                tool_call_id=str(data.get("tool_call_id", "")),
                success=bool(data.get("success", False)),
            )
        )
    elif kind == "tool_evidence":
        tool_evidence.append(
            ToolEvidenceRecord(
                run_id=str(data.get("run_id", "")) or None,
                tool_name=str(data.get("tool", "")),
                tool_call_id=str(data.get("tool_call_id", "")),
                content=str(data.get("content", "")),
                outcome=str(data.get("outcome", "")),
            )
        )
    elif kind == "llm_usage":
        llm_usage.append(
            LlmUsageRecord(
                run_id=str(data.get("run_id", "")),
                model_name=str(data.get("model_name", "")),
                provider_name=str(data.get("provider_name", "")),
                input_tokens=int(data.get("input_tokens", 0)),
                output_tokens=int(data.get("output_tokens", 0)),
                cache_read_tokens=int(data.get("cache_read_tokens", 0)),
                cache_write_tokens=int(data.get("cache_write_tokens", 0)),
                requests=int(data.get("requests", 0)),
            )
        )
    elif kind == "error":
        errors.append(str(data.get("content", "Unknown application error")))


def _websocket_url(system_url: str) -> str:
    parsed = urlsplit(system_url.rstrip("/"))
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError(f"Invalid running-system URL: {system_url!r}")
    scheme = {
        "http": "ws",
        "https": "wss",
        "ws": "ws",
        "wss": "wss",
    }[parsed.scheme]
    return urlunsplit((scheme, parsed.netloc, "/ws/chat", "", ""))
