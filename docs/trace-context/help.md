# Actor trace-context propagation

Pydantic Evals records spans emitted while each task runs. Akgentic executes
agents in Pykka worker threads, and Python context variables do not cross that
thread boundary automatically. Without propagation, Pydantic AI still emits
model and tool spans, but they are detached from the evaluation case and absent
from `EvaluatorContext.span_tree`.

Knowledge Akgents restores that connection in
`src/knowledge_akgents/trace_context.py`.

## How it works

Before an in-process actor message is sent, the application stores a
`contextvars.copy_context()` snapshot on a private message attribute. The
receiving application-owned `BaseAgent` and `HumanProxy` subclasses execute the
normal Akgentic handler inside a fresh copy of that snapshot.

This propagates both:

- the active OpenTelemetry span context, which preserves parent-child
  relationships;
- Pydantic Evals' span-collector context variable, which makes spans available
  through `ctx.span_tree`.

The initial browser or evaluation message is captured in
`KnowledgeTeam.send()`. Messages created by agents are captured by the
overridden `send()` methods. Existing context is preserved when the HumanProxy
forwards a pre-formed message.

## Why not only use `traceparent`

W3C `traceparent` propagation reconnects OpenTelemetry trace and parent IDs, but
Pydantic Evals also uses an in-process context variable to decide which
evaluation case should collect a finished span. Propagating only W3C headers
would produce a connected trace without populating the case's `span_tree`.

## Scope and limitation

The private context snapshot is intentionally omitted from message
serialization. Python `Context` objects are process-local and cannot be safely
serialized.

This implementation therefore supports the current local Pykka thread runtime.
A future process-based, remote, or persisted-message transport needs a
framework-level carrier containing standard OpenTelemetry propagation fields
plus an explicit mechanism for associating remote spans with an evaluation
case. It must not attempt to serialize a Python `Context`.

## Verification

The deterministic regression test starts an OpenTelemetry child span on a
separate thread and verifies that Pydantic Evals' context-subtree collector sees
it with the correct parent.

The paid fixture-backed `jettro-profession` verification captured eight spans,
including:

- `invoke_agent agent`;
- `chat gpt-5.6-luna`;
- `execute_tool search_graph`.

The saved local report is
`eval-reports/trace-context-verification.json`. Reports are gitignored because
they may contain prompts, answers, retrieved evidence, and tool arguments.
