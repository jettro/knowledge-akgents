# Creating evaluation datasets

For a normal retrieval evaluation, you author one JSON file in
`evals/datasets/`. You do not add Python, register a scenario, or implement a
task runner.

The file answers three questions:

1. Which knowledge should the production-like team query?
2. Which questions should be asked?
3. Which observable results make each answer acceptable?

Add `"$schema": "./schema.json"` for editor validation and completion.

## Evaluate a real, already-ingested page

If the page is already present in the application's Qdrant collection, select
the existing store:

```json
{
  "$schema": "./schema.json",
  "version": 2,
  "task": "retrieval",
  "name": "knowledge-akgents/new-page",
  "knowledge": {
    "source": "running_system"
  },
  "default_metadata": {
    "source_url": "https://example.com/about",
    "purpose": "post-ingestion-acceptance"
  },
  "cases": [
    {
      "name": "organization-purpose",
      "message": "What does Example Company do?",
      "evaluators": [
        {
          "type": "human_response_contains_terms",
          "required_terms": ["reviewed", "expected", "terms"]
        }
      ]
    },
    {
      "name": "organization-purpose-paraphrase",
      "message": "How does Example Company help its customers?",
      "metadata": {
        "prompt_variant": "paraphrase"
      },
      "evaluators": [
        {
          "type": "human_response_contains_any_term",
          "accepted_terms": ["accepted phrase", "equivalent wording"]
        }
      ]
    }
  ]
}
```

`running_system` means:

- call the already-running Knowledge Akgents backend over `/ws/chat`;
- use the live production team that owns the ingested Qdrant points;
- call its real `search_graph` tool;
- do not preload or replace knowledge;
- do not call Tavily or ingest the page during the evaluation.

Run it with:

```bash
make eval-live-dataset \
  DATASET=evals/datasets/new_page.json \
  EVAL_FLAGS="--save-report eval-reports/new-page.json"
```

The application must already be running and the page must already be ingested.
Retrieval cases are read-only: shared dataset evaluators fail if the team calls
`update_graph` or the web tool.

The default backend is `http://localhost:8000`. Override it when needed:

```bash
make eval-live-dataset \
  DATASET=evals/datasets/new_page.json \
  SYSTEM_URL=https://knowledge.example.com
```

Run this evaluation while the application is otherwise idle. The current
WebSocket bridge broadcasts team events to connected clients, so concurrent
chat traffic could be included in the evidence stream.

## Evaluate against controlled records

Use fixtures when you want repeatable agent tests without depending on Qdrant:

```json
{
  "$schema": "./schema.json",
  "version": 2,
  "task": "retrieval",
  "name": "knowledge-akgents/people",
  "knowledge": {
    "source": "fixtures",
    "default_fixture": "people",
    "fixtures": {
      "people": {
        "records": [
          {
            "name": "Jane Doe",
            "entity_type": "Person",
            "description": "Jane Doe is a software engineer."
          }
        ]
      }
    }
  },
  "cases": [
    {
      "name": "jane-role",
      "message": "What role does Jane Doe have?",
      "evaluators": [
        {
          "type": "human_response_contains_terms",
          "required_terms": ["software engineer"]
        }
      ]
    }
  ]
}
```

Run controlled data with:

```bash
make eval-dataset DATASET=evals/datasets/people.json
```

This selects the evaluation catalog team and replaces only its read-only
knowledge tool with the declared records.

## How results are evaluated

Every JSON retrieval case automatically checks:

- the team completed with a response to the human;
- the message followed `Human → Manager → Knowledge → Manager → Human`;
- `search_graph` was called at least once and returned successfully;
- no web-fetch or graph-update tool was called;
- tool-call arguments parsed correctly and actor execution did not fail.

Case evaluators then check the answer-specific contract:

| Evaluator | Use |
|---|---|
| `human_response_contains_terms` | Every listed term must occur in the answer |
| `human_response_contains_any_term` | At least one reviewed alternative must occur |
| `tool_evidence_contains_terms` | Required terms must occur in the real tool result |
| `tool_call_count` | Constrain how often a named tool may be called |

These are deterministic acceptance checks. Add `--with-judges` when you also
want paid groundedness and answer-relevance judgments against the captured
`search_graph` evidence.

Judges complement rather than replace source-derived checks. A grounded answer
that correctly says “the retrieved evidence does not contain that fact” may
score well for groundedness and relevance while still failing the dataset's
expected-fact assertion. That combination usually identifies an ingestion or
retrieval gap rather than answer hallucination.

The exported Pydantic Evals report contains each case input, answer, tool calls,
tool results, assertion outcomes, reasons, usage measurements, and spans. Open
it with `make eval-viewer`.

## Designing useful cases for a new page

Start with a small acceptance suite:

1. A canonical question for each important fact.
2. A paraphrase for the most important question.
3. A multi-fact question that requires combining retrieved knowledge.
4. A missing-fact question that should not be invented.
5. A wording vocabulary when several answers are equally correct.

Expected terms must come from facts you reviewed on the source page, not from
the model's previous answer. A passing result means the complete team routed,
searched, returned evidence, and produced an answer satisfying those reviewed
expectations.

When the JSON vocabulary cannot represent a requirement, add or reuse an
evaluator in `evals/evaluators/` and extend the strict loader in
`evals/harness/dataset_loader.py`. Multi-turn ingestion and controlled failure
state machines belong in `evals/scenarios/`, not `evals/datasets/`.
