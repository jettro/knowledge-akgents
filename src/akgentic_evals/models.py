"""Normalized evidence produced by an Akgentic evaluation runtime."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageRecord(BaseModel):
    sender: str | None
    recipient: str | None
    message_type: str
    content: str


class ToolInvocationId(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    tool_call_id: str


class ToolCallRecord(BaseModel):
    run_id: str
    tool_name: str
    tool_call_id: str
    arguments_raw: str
    arguments: Any = None
    parse_error: str | None = None

    @property
    def invocation_id(self) -> ToolInvocationId:
        return ToolInvocationId(run_id=self.run_id, tool_call_id=self.tool_call_id)


class ToolReturnRecord(BaseModel):
    run_id: str
    tool_name: str
    tool_call_id: str
    success: bool

    @property
    def invocation_id(self) -> ToolInvocationId:
        return ToolInvocationId(run_id=self.run_id, tool_call_id=self.tool_call_id)


class ToolEvidenceRecord(BaseModel):
    run_id: str | None
    tool_name: str
    tool_call_id: str
    content: str
    outcome: str

    @property
    def invocation_id(self) -> ToolInvocationId | None:
        if self.run_id is None:
            return None
        return ToolInvocationId(run_id=self.run_id, tool_call_id=self.tool_call_id)


class ToolInvocation(BaseModel):
    id: ToolInvocationId
    tool_name: str
    call: ToolCallRecord | None = None
    result: ToolReturnRecord | None = None
    evidence: list[ToolEvidenceRecord] = Field(default_factory=list)

    @property
    def returned(self) -> bool:
        return self.result is not None

    @property
    def success(self) -> bool:
        return self.result is not None and self.result.success


class LlmUsageRecord(BaseModel):
    run_id: str
    model_name: str
    provider_name: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    requests: int


class AkgenticCaseOutput(BaseModel):
    final_response: str | None
    human_responses: list[str]
    completion_reason: str
    messages: list[MessageRecord]
    tool_calls: list[ToolCallRecord]
    tool_returns: list[ToolReturnRecord]
    tool_evidence: list[ToolEvidenceRecord] = Field(default_factory=list)
    llm_usage: list[LlmUsageRecord] = Field(default_factory=list)
    errors: list[str]

    def tool_invocations(
        self,
        *,
        tool_name: str | None = None,
        successful: bool | None = None,
    ) -> list[ToolInvocation]:
        calls = {record.invocation_id: record for record in self.tool_calls}
        returns = {record.invocation_id: record for record in self.tool_returns}
        evidence: dict[ToolInvocationId, list[ToolEvidenceRecord]] = defaultdict(list)
        for record in self.tool_evidence:
            if record.invocation_id is not None:
                evidence[record.invocation_id].append(record)

        invocation_ids = calls.keys() | returns.keys() | evidence.keys()
        invocations = [
            ToolInvocation(
                id=invocation_id,
                tool_name=_tool_name(
                    calls.get(invocation_id),
                    returns.get(invocation_id),
                    evidence.get(invocation_id, []),
                ),
                call=calls.get(invocation_id),
                result=returns.get(invocation_id),
                evidence=evidence.get(invocation_id, []),
            )
            for invocation_id in invocation_ids
        ]
        return [
            invocation
            for invocation in invocations
            if (tool_name is None or invocation.tool_name == tool_name)
            and (successful is None or invocation.success is successful)
        ]

    def successful_tool_evidence(self, tool_name: str) -> list[ToolEvidenceRecord]:
        return [
            record
            for invocation in self.tool_invocations(tool_name=tool_name, successful=True)
            for record in invocation.evidence
        ]


def _tool_name(
    call: ToolCallRecord | None,
    result: ToolReturnRecord | None,
    evidence: list[ToolEvidenceRecord],
) -> str:
    if call is not None:
        return call.tool_name
    if result is not None:
        return result.tool_name
    return evidence[0].tool_name
