# Evaluation architecture

There are four distinct layers. Only three are implemented in this repository.

| Layer | Location | Responsibility |
|---|---|---|
| Pydantic Evals framework | Installed `pydantic-evals` package | `Dataset`, `Case`, experiment execution, reports, spans, and evaluator APIs |
| Knowledge Akgents harness | `evals/harness/` | Starts teams, optionally injects controlled tools, collects events, loads JSON datasets, and saves reports |
| Application evaluation policy | `evals/evaluators/` | Defines what correct Knowledge Akgents routing, tool usage, and answers mean |
| Evaluation content | `evals/datasets/` and `evals/fixtures/` | JSON case definitions and raw controlled web content |
| Executable scenarios | `evals/scenarios/` | Python orchestration for multi-turn ingestion, failures, and state transitions |

Command-line entry points live separately in `evals/runners/`.

## Evaluation data

Evaluation data describes scenarios and expected outcomes:

- questions and multi-turn conversations;
- reviewed fixture knowledge;
- expected answer terms;
- expected or forbidden tools;
- tool-call limits;
- human labels used to calibrate judges;
- metadata such as `canonical`, `paraphrase`, or `negative-control`.

`evals/datasets/` is deliberately data-only. It contains JSON case definitions,
its JSON Schema, and a short authoring README. A dataset selects either
controlled fixture records or an already-populated real knowledge store.
Adding another retrieval dataset does not require a Python module or runner
registration.

Specialized multi-turn ingestion, failure, and change-detection scenarios still
live under `evals/scenarios/` because their ordered tool-state transitions are
executable orchestration rather than dataset content.

In this repository, the terms mean:

- **Dataset** — the Pydantic Evals concept: a collection of cases and shared
  evaluators. Our JSON file is a project schema that is converted into a
  Pydantic Evals `Dataset`.
- **Case** — the Pydantic Evals concept: one input scenario with metadata and
  optional case-specific evaluators.
- **Fixture** — a Knowledge Akgents testing concept: controlled knowledge or
  web content supplied to the task instead of a live dependency. Pydantic Evals
  does not prescribe this fixture abstraction.

## Knowledge Akgents evaluation logic

This repository supplies the domain-specific behavior that Pydantic Evals does
not know about:

- `evals/harness/tasks.py` starts a `KnowledgeTeam` for a case;
- `evals/harness/dataset_loader.py` validates JSON and selects fixture or real-store execution;
- `evals/harness/catalog.py` selects the evaluation or production catalog team and
  applies deterministic fixture tools only to the evaluation team;
- `evals/harness/collector.py` converts Akgentic events into a stable result;
- `evals/evaluators/events.py` checks routes, tools, arguments, counts, and
  responses;
- `evals/evaluators/live.py` judges answers against captured `search_graph`
  evidence;
- fixture tools isolate agent behavior from Tavily and production Qdrant.

Change `harness/` when execution or evidence collection changes. Change
`evaluators/` when the definition of correct application behavior changes.
Ordinary new retrieval cases should require changes only under `datasets/`.

## Pydantic Evals framework

Pydantic Evals supplies:

- `Dataset` and `Case`;
- evaluator execution;
- `LLMJudge`;
- repetitions and concurrency;
- result aggregation and reports;
- baseline comparison and optional Logfire integration.

The framework runs evaluations, but it does not define what a correct
Knowledge Akgents answer or tool call looks like. Those rules belong to the
case data and repository-specific evaluators.

No Pydantic Evals framework implementation is copied into this repository.
The harness only adapts the application's actor runtime and fixture tools to
the framework's public APIs.

## Catalog and fixture datasets

The Akgentic catalog and evaluation dataset JSON solve different problems:

- `akgentic-catalog` YAML entries define the team, agents, prompts, shared
  model defaults, and tools;
- evaluation JSON defines reviewed knowledge, questions, expected behavior,
  and metadata;
- Python will continue to contain task adapters and reusable evaluators;
- Pydantic Evals will continue to execute the resulting cases and reports.

Keeping these responsibilities separate prevents test expectations from
becoming part of the production team configuration.

## Evaluation tiers

Fixture JSON loads `knowledge-akgents-evaluation` and replaces its read-only
knowledge tool with controlled records. It is repeatable apart from model
behavior and does not call Tavily.

Running-system JSON sends questions through the live backend WebSocket. The
already-running production team queries its own Qdrant-scoped data with the
real `search_graph` tool. The page must already have been ingested.

The production end-to-end tier loads
`knowledge-akgents-production` unchanged. It uses temporary ingestion state and
in-memory Qdrant by default, while exercising the real production web tool.
Loading the production namespace never authorizes production mutable storage:
persistent Qdrant requires an explicit runner flag.
