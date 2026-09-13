"""Tests for context propagation across actor thread boundaries."""

from __future__ import annotations

import threading
from contextvars import ContextVar

import logfire
from akgentic.agent import AgentMessage
from opentelemetry import trace
from pydantic_evals.otel._context_subtree import context_subtree

from knowledge_akgents.trace_context import (
    attach_message_context,
    run_in_message_context,
)


def test_message_context_preserves_the_original_snapshot() -> None:
    value = ContextVar("trace_context_test_value", default="missing")
    token = value.set("captured")
    try:
        message = AgentMessage(content="test")
        attach_message_context(message)
        value.set("changed")

        observed = run_in_message_context(message, value.get)
    finally:
        value.reset(token)

    assert observed == "captured"
    assert "_knowledge_akgents_context" not in message.model_dump()


def test_message_context_captures_actor_thread_spans_for_evaluations() -> None:
    logfire.configure(send_to_logfire=False, console=False)
    tracer = trace.get_tracer(__name__)
    message = AgentMessage(content="test")

    with context_subtree() as span_tree:
        with tracer.start_as_current_span("evaluation-case"):
            attach_message_context(message)

            def actor_work() -> None:
                run_in_message_context(
                    message,
                    lambda: _record_span(tracer),
                )

            thread = threading.Thread(target=actor_work)
            thread.start()
            thread.join()

    spans = {node.name: node for node in span_tree}
    assert spans["actor-work"].parent_span_id == spans["evaluation-case"].span_id


def _record_span(tracer: trace.Tracer) -> None:
    with tracer.start_as_current_span("actor-work"):
        pass
