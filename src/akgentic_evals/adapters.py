"""Adapt framework-specific events to normalized evaluation events."""

from __future__ import annotations

import json
from typing import Any

from akgentic.agent import AgentMessage
from akgentic.core.messages.orchestrator import ErrorMessage, EventMessage, SentMessage
from akgentic.llm import LlmMessageEvent, LlmUsageEvent, ToolCallEvent, ToolReturnEvent
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from akgentic_evals.events import (
    AkgenticEvalEvent,
    MessageObserved,
    RuntimeFailed,
    RuntimeStopped,
    ToolCalled,
    ToolEvidenceObserved,
    ToolReturned,
    UsageObserved,
)
from akgentic_evals.runtime import EventHandler


class AkgenticEventAdapter:
    """Translate framework events into the reusable normalized event stream."""

    def __init__(self, event_handler: EventHandler) -> None:
        self._event_handler = event_handler

    def _emit(self, event: AkgenticEvalEvent) -> None:
        self._event_handler(event)

    def set_restoring(self, team_id: Any, restoring: bool) -> None:  # noqa: FBT001
        pass

    def on_stop(self, team_id: Any) -> None:
        pass

    def on_stop_request(self, team_id: Any) -> None:
        self._emit(RuntimeStopped())

    def on_message(self, message: Any) -> None:
        if isinstance(message, SentMessage):
            self._record_sent_message(message)
        elif isinstance(message, EventMessage):
            self._record_domain_event(message.event)
        elif isinstance(message, ErrorMessage):
            error = f"{message.content_type or 'Error'}: {message.content}".strip()
            self._emit(RuntimeFailed(error=error))

    def _record_sent_message(self, message: SentMessage) -> None:
        payload = message.message
        if not isinstance(payload, AgentMessage):
            return
        self._emit(
            MessageObserved(
                sender=_address_name(message.sender),
                recipient=_address_name(message.recipient),
                message_type=payload.type,
                content=payload.content,
            )
        )

    def _record_domain_event(self, event: Any) -> None:
        if isinstance(event, ToolCallEvent):
            try:
                arguments = json.loads(event.arguments)
                parse_error = None
            except json.JSONDecodeError as exc:
                arguments = None
                parse_error = str(exc)
            self._emit(
                ToolCalled(
                    run_id=event.run_id,
                    tool_name=event.tool_name,
                    tool_call_id=event.tool_call_id,
                    arguments_raw=event.arguments,
                    arguments=arguments,
                    parse_error=parse_error,
                )
            )
        elif isinstance(event, ToolReturnEvent):
            self._emit(
                ToolReturned(
                    run_id=event.run_id,
                    tool_name=event.tool_name,
                    tool_call_id=event.tool_call_id,
                    success=event.success,
                )
            )
        elif isinstance(event, LlmUsageEvent):
            self._emit(
                UsageObserved(
                    run_id=event.run_id,
                    model_name=event.model_name,
                    provider_name=event.provider_name,
                    input_tokens=event.input_tokens,
                    output_tokens=event.output_tokens,
                    cache_read_tokens=event.cache_read_tokens,
                    cache_write_tokens=event.cache_write_tokens,
                    requests=event.requests,
                )
            )
        elif isinstance(event, LlmMessageEvent):
            self._record_llm_message(event)

    def _record_llm_message(self, event: LlmMessageEvent) -> None:
        message = event.message
        if not isinstance(message, ModelRequest):
            return
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                self._emit(
                    ToolEvidenceObserved(
                        run_id=message.run_id,
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id,
                        content=_stringify_tool_content(part.content),
                        outcome=part.outcome,
                    )
                )


def _address_name(address: Any) -> str | None:
    return getattr(address, "name", None)


def _stringify_tool_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
