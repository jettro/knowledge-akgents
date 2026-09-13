"""Typed inputs and outputs shared by Knowledge Akgents evaluations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from evals.harness.fixture_knowledge import KnowledgeFixture


class TeamTurn(BaseModel):
    message: str
    target: str | None = None


class TeamCaseInput(BaseModel):
    message: str | None = None
    target: str | None = None
    turns: list[TeamTurn] = Field(default_factory=list)
    timeout_seconds: float = 180.0
    fixture_source_url: str | None = None
    fixture_path: str | None = None
    fixture_paths: list[str] = Field(default_factory=list)
    fixture_web_failure: str | None = None
    knowledge_fixture: KnowledgeFixture | None = None
    knowledge_fixture_path: str | None = None

    @model_validator(mode="after")
    def validate_turns(self) -> TeamCaseInput:
        if bool(self.message) == bool(self.turns):
            raise ValueError("Provide either message or turns")
        if self.knowledge_fixture is not None and self.knowledge_fixture_path is not None:
            raise ValueError("Provide either knowledge_fixture or knowledge_fixture_path")
        return self

    def ordered_turns(self) -> list[TeamTurn]:
        if self.turns:
            return self.turns
        assert self.message is not None
        return [TeamTurn(message=self.message, target=self.target)]


class MessageRecord(BaseModel):
    sender: str | None
    recipient: str | None
    message_type: str
    content: str


class ToolCallRecord(BaseModel):
    run_id: str
    tool_name: str
    tool_call_id: str
    arguments_raw: str
    arguments: Any = None
    parse_error: str | None = None


class ToolReturnRecord(BaseModel):
    run_id: str
    tool_name: str
    tool_call_id: str
    success: bool


class ToolEvidenceRecord(BaseModel):
    run_id: str | None
    tool_name: str
    tool_call_id: str
    content: str
    outcome: str


class LlmUsageRecord(BaseModel):
    run_id: str
    model_name: str
    provider_name: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    requests: int


class TeamCaseOutput(BaseModel):
    final_response: str | None
    human_responses: list[str]
    completion_reason: str
    messages: list[MessageRecord]
    tool_calls: list[ToolCallRecord]
    tool_returns: list[ToolReturnRecord]
    tool_evidence: list[ToolEvidenceRecord] = Field(default_factory=list)
    llm_usage: list[LlmUsageRecord] = Field(default_factory=list)
    errors: list[str]
