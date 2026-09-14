# Evaluation datasets

This directory is the authoring surface for evaluation data. It contains only:

- `*.json`: questions, expected outcomes, and knowledge-source selection;
- `schema.json`: editor validation and completion for those files.

Python execution code does not belong here:

- generic JSON validation and conversion lives in `evals/harness/dataset_loader.py`;
- reusable correctness rules live in `evals/evaluators/`;
- executable multi-step or failure simulations live in `evals/scenarios/`;
- command-line entry points live in `evals/runners/`.

## Real knowledge store

Use the already-running application and its real knowledge tool:

```json
{
  "$schema": "./schema.json",
  "version": 2,
  "task": "retrieval",
  "name": "knowledge-akgents/my-page",
  "knowledge": {"source": "running_system"},
  "cases": [
    {
      "name": "page-purpose",
      "message": "What does the organization do?",
      "evaluators": [
        {
          "type": "human_response_contains_terms",
          "required_terms": ["reviewed", "answer", "terms"]
        }
      ]
    }
  ]
}
```

This mode does not fake or preload knowledge. It sends cases through the
already-running application's WebSocket endpoint, so the same live team that
owns the Qdrant points performs the search.

## Controlled knowledge

Use `"source": "fixtures"` when the purpose is to evaluate agent behavior
against small, deterministic records rather than a real Qdrant collection.

See `retrieval_only.json` for a complete example.

`rag4j_documentation.json` is the concrete running-system example. It evaluates
the already-ingested RAG4j/p documentation page and checks both retrieved tool
evidence and final answers.
