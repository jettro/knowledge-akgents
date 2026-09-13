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

Run any self-contained retrieval fixture dataset without registering a Python
scenario:

```bash
make eval-fixture FIXTURE_DATASET=evals/fixtures/people.json
```

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

Logfire export is explicit:

```bash
make eval-retrieval EVAL_FLAGS="--send-to-logfire"
```

Review the data policy before exporting fixtures, prompts, or retrieved
content.
