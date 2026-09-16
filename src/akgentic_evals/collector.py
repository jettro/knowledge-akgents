"""Thread-safe collection of normalized Akgentic evaluation events."""

from __future__ import annotations

import threading
import time

from akgentic_evals.completion import CompletionPolicy, MessageResponseCompletion
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
from akgentic_evals.models import (
    AkgenticCaseOutput,
    LlmUsageRecord,
    MessageRecord,
    ToolCallRecord,
    ToolEvidenceRecord,
    ToolReturnRecord,
)


class EvaluationEventCollector:
    """Collect normalized evidence and wait for application responses."""

    def __init__(
        self,
        *,
        completion_policy: CompletionPolicy | None = None,
    ) -> None:
        self._completion_policy = completion_policy or MessageResponseCompletion()
        self._condition = threading.Condition()
        self._messages: list[MessageRecord] = []
        self._tool_calls: list[ToolCallRecord] = []
        self._tool_returns: list[ToolReturnRecord] = []
        self._tool_evidence: list[ToolEvidenceRecord] = []
        self._llm_usage: list[LlmUsageRecord] = []
        self._errors: list[str] = []
        self._responses: list[str] = []
        self._stopped = False

    @property
    def completion_reason(self) -> str:
        return self._completion_policy.reason

    def on_event(self, event: AkgenticEvalEvent) -> None:
        with self._condition:
            if isinstance(event, MessageObserved):
                self._record_message(event)
            elif isinstance(event, ToolCalled):
                self._tool_calls.append(
                    ToolCallRecord(
                        run_id=event.run_id,
                        tool_name=event.tool_name,
                        tool_call_id=event.tool_call_id,
                        arguments_raw=event.arguments_raw,
                        arguments=event.arguments,
                        parse_error=event.parse_error,
                    )
                )
            elif isinstance(event, ToolReturned):
                self._tool_returns.append(
                    ToolReturnRecord(
                        run_id=event.run_id,
                        tool_name=event.tool_name,
                        tool_call_id=event.tool_call_id,
                        success=event.success,
                    )
                )
            elif isinstance(event, ToolEvidenceObserved):
                self._tool_evidence.append(
                    ToolEvidenceRecord(
                        run_id=event.run_id,
                        tool_name=event.tool_name,
                        tool_call_id=event.tool_call_id,
                        content=event.content,
                        outcome=event.outcome,
                    )
                )
            elif isinstance(event, UsageObserved):
                self._llm_usage.append(
                    LlmUsageRecord(
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
            elif isinstance(event, RuntimeFailed):
                self._errors.append(event.error)
                self._condition.notify_all()
            elif isinstance(event, RuntimeStopped):
                self._stopped = True
                self._condition.notify_all()

    def wait_for_responses(
        self,
        expected_count: int,
        timeout_seconds: float,
    ) -> AkgenticCaseOutput:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while (
                len(self._responses) < expected_count
                and not self._errors
                and not self._stopped
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)

            if len(self._responses) >= expected_count:
                completion_reason = self.completion_reason
            elif self._errors:
                completion_reason = "error"
            elif self._stopped:
                completion_reason = "team_stopped"
            else:
                completion_reason = "timeout"

            return AkgenticCaseOutput(
                final_response=self._responses[-1] if self._responses else None,
                human_responses=list(self._responses),
                completion_reason=completion_reason,
                messages=list(self._messages),
                tool_calls=list(self._tool_calls),
                tool_returns=list(self._tool_returns),
                tool_evidence=list(self._tool_evidence),
                llm_usage=list(self._llm_usage),
                errors=list(self._errors),
            )

    def _record_message(self, event: MessageObserved) -> None:
        self._messages.append(
            MessageRecord(
                sender=event.sender,
                recipient=event.recipient,
                message_type=event.message_type,
                content=event.content,
            )
        )
        response = self._completion_policy.response_content(event)
        if response is not None:
            self._responses.append(response)
            self._condition.notify_all()
