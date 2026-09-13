"""Thread-safe collection of Akgentic evaluation evidence."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from akgentic.agent import AgentMessage
from akgentic.core.messages.orchestrator import ErrorMessage, EventMessage, SentMessage
from akgentic.llm import LlmMessageEvent, LlmUsageEvent, ToolCallEvent, ToolReturnEvent
from pydantic_ai.messages import ModelRequest, ToolReturnPart

from evals.models import (
    LlmUsageRecord,
    MessageRecord,
    TeamCaseOutput,
    ToolCallRecord,
    ToolEvidenceRecord,
    ToolReturnRecord,
)


class EvaluationEventCollector:
    """Collect raw orchestration evidence and signal when the human receives a result."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._messages: list[MessageRecord] = []
        self._tool_calls: list[ToolCallRecord] = []
        self._tool_returns: list[ToolReturnRecord] = []
        self._tool_evidence: list[ToolEvidenceRecord] = []
        self._llm_usage: list[LlmUsageRecord] = []
        self._errors: list[str] = []
        self._human_responses: list[str] = []
        self._stopped = False

    def set_restoring(self, team_id: Any, restoring: bool) -> None:  # noqa: FBT001
        pass

    def on_stop(self, team_id: Any) -> None:
        pass

    def on_stop_request(self, team_id: Any) -> None:
        with self._condition:
            self._stopped = True
            self._condition.notify_all()

    def on_message(self, message: Any) -> None:
        if isinstance(message, SentMessage):
            self._record_sent_message(message)
        elif isinstance(message, EventMessage):
            self._record_domain_event(message.event)
        elif isinstance(message, ErrorMessage):
            self._record_error(message)

    def wait(self, timeout_seconds: float) -> TeamCaseOutput:
        return self.wait_for_human_responses(1, timeout_seconds)

    def wait_for_human_responses(
        self,
        expected_count: int,
        timeout_seconds: float,
    ) -> TeamCaseOutput:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while (
                len(self._human_responses) < expected_count
                and not self._errors
                and not self._stopped
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)

            if len(self._human_responses) >= expected_count:
                completion_reason = "human_response"
            elif self._errors:
                completion_reason = "error"
            elif self._stopped:
                completion_reason = "team_stopped"
            else:
                completion_reason = "timeout"

            return TeamCaseOutput(
                final_response=self._human_responses[-1] if self._human_responses else None,
                human_responses=list(self._human_responses),
                completion_reason=completion_reason,
                messages=list(self._messages),
                tool_calls=list(self._tool_calls),
                tool_returns=list(self._tool_returns),
                tool_evidence=list(self._tool_evidence),
                llm_usage=list(self._llm_usage),
                errors=list(self._errors),
            )

    def _record_sent_message(self, message: SentMessage) -> None:
        payload = message.message
        if not isinstance(payload, AgentMessage):
            return

        sender = _address_name(message.sender)
        recipient = _address_name(message.recipient)
        record = MessageRecord(
            sender=sender,
            recipient=recipient,
            message_type=payload.type,
            content=payload.content,
        )

        with self._condition:
            self._messages.append(record)
            if recipient == "@Human" and sender != "@Human" and payload.content:
                self._human_responses.append(payload.content)
                self._condition.notify_all()

    def _record_domain_event(self, event: Any) -> None:
        if isinstance(event, ToolCallEvent):
            try:
                arguments = json.loads(event.arguments)
                parse_error = None
            except json.JSONDecodeError as exc:
                arguments = None
                parse_error = str(exc)

            record = ToolCallRecord(
                run_id=event.run_id,
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                arguments_raw=event.arguments,
                arguments=arguments,
                parse_error=parse_error,
            )
            with self._condition:
                self._tool_calls.append(record)
        elif isinstance(event, ToolReturnEvent):
            record = ToolReturnRecord(
                run_id=event.run_id,
                tool_name=event.tool_name,
                tool_call_id=event.tool_call_id,
                success=event.success,
            )
            with self._condition:
                self._tool_returns.append(record)
        elif isinstance(event, LlmUsageEvent):
            record = LlmUsageRecord(
                run_id=event.run_id,
                model_name=event.model_name,
                provider_name=event.provider_name,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                cache_read_tokens=event.cache_read_tokens,
                cache_write_tokens=event.cache_write_tokens,
                requests=event.requests,
            )
            with self._condition:
                self._llm_usage.append(record)
        elif isinstance(event, LlmMessageEvent):
            self._record_llm_message(event)

    def _record_llm_message(self, event: LlmMessageEvent) -> None:
        message = event.message
        if not isinstance(message, ModelRequest):
            return

        records = [
            ToolEvidenceRecord(
                run_id=message.run_id,
                tool_name=part.tool_name,
                tool_call_id=part.tool_call_id,
                content=_stringify_tool_content(part.content),
                outcome=part.outcome,
            )
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        if records:
            with self._condition:
                self._tool_evidence.extend(records)

    def _record_error(self, message: ErrorMessage) -> None:
        error = f"{message.content_type or 'Error'}: {message.content}".strip()
        with self._condition:
            self._errors.append(error)
            self._condition.notify_all()


def _address_name(address: Any) -> str | None:
    return getattr(address, "name", None)


def _stringify_tool_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)
