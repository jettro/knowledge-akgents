# Running evaluations

## Deterministic harness checks

These tests do not require network or model calls:

```bash
make test-evals
```

Use them after changing datasets, fixture tools, collectors, evaluators, or
runner behavior.

## Live scenarios

```bash
make eval-ingestion
make eval-jettro
make eval-yuma
make eval-prompt-injection
make eval-no-useful-content
make eval-unreachable-url
make eval-routing
make eval-change-aware-ingestion
make eval-retrieval
```

These commands require model credentials and make paid calls. The standard
targets force in-memory knowledge storage and do not export to Logfire.

Run a JSON dataset against controlled records:

```bash
make eval-dataset DATASET=evals/datasets/people.json
```

Run JSON cases through the already-running production application and its
Qdrant-backed knowledge tool:

```bash
make eval-live-dataset \
  DATASET=evals/datasets/new_page.json \
  EVAL_FLAGS="--save-report eval-reports/new-page.json"
```

The dataset must declare `"knowledge": {"source": "running_system"}`. This
path sends questions through the running application's WebSocket API. It does
not ingest or preload knowledge and expects the required page to have been
ingested already.

Use `SYSTEM_URL=...` for a backend not running at `http://localhost:8000`.
Avoid concurrent chat activity during the run because the current application
event stream is broadcast rather than session-scoped.

Select one case:

```bash
make eval-retrieval EVAL_FLAGS="--case jettro-profession"
```

Repeat cases to inspect model variance:

```bash
make eval-retrieval EVAL_FLAGS="--case jettro-profession --repeat 3"
```

## Live judges

Add calibrated groundedness and answer-relevance judgments:

```bash
make eval-retrieval \
  EVAL_FLAGS="--case jettro-profession --with-judges"
```

Each case adds two paid judge calls. Judge usage is separate from the
event-derived agent usage shown in the report.

## Reports and Logfire

Save and compare native Pydantic Evals reports:

```bash
make eval-retrieval \
  EVAL_FLAGS="--save-report eval-reports/retrieval-baseline.json"
make eval-retrieval \
  EVAL_FLAGS="--baseline eval-reports/retrieval-baseline.json"
```

Raw reports are gitignored because they can contain prompts, answers, retrieved
evidence, and tool arguments.

The command-line table is the immediate evaluation result. Each assertion is
produced by either a shared behavioral evaluator (completion, route, real tool
use, tool success, forbidden writes) or a case-specific answer evaluator from
the JSON. Save the report when the result needs to be reviewed, compared, or
shared locally:

```bash
make eval-live-dataset \
  DATASET=evals/datasets/new_page.json \
  EVAL_FLAGS="--save-report eval-reports/new-page.json"
make eval-viewer
```

Logfire export is explicit:

```bash
make eval-retrieval EVAL_FLAGS="--send-to-logfire"
```

Review the data policy before exporting fixtures, prompts, or retrieved
content.
