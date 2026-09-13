# Evaluation architecture

The evaluation harness has three layers. Keeping these layers distinct makes it
clear what contributors should change.

## Evaluation data

Evaluation data describes scenarios and expected outcomes:

- questions and multi-turn conversations;
- reviewed fixture knowledge;
- expected answer terms;
- expected or forbidden tools;
- tool-call limits;
- human labels used to calibrate judges;
- metadata such as `canonical`, `paraphrase`, or `negative-control`.

This data currently lives in Python under `evals/datasets/` and in JSON or text
files under `evals/fixtures/`.

## Knowledge Akgents evaluation logic

This repository supplies the domain-specific behavior that Pydantic Evals does
not know about:

- `evals/tasks.py` starts a `KnowledgeTeam` for a case;
- `evals/collector.py` converts Akgentic events into a stable result;
- `evals/event_evaluators.py` checks routes, tools, arguments, counts, and
  responses;
- `evals/live_judges.py` judges answers against captured `search_graph`
  evidence;
- fixture tools isolate agent behavior from Tavily and production Qdrant.

Change this layer only when a new type of behavior cannot be represented with
the existing inputs and evaluators.

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

## Catalog and evaluation cases

The planned Akgentic catalog migration and the evaluation-case migration solve
different problems:

- catalog YAML defines the team, agents, prompts, tools, and environment
  profile;
- evaluation YAML will define questions, fixtures, expected behavior, and
  metadata;
- Python will continue to contain task adapters and reusable evaluators;
- Pydantic Evals will continue to execute the resulting cases and reports.

Keeping these responsibilities separate prevents test expectations from
becoming part of the production team configuration.
