# Evaluation report viewer

The local report viewer provides a richer view of native Pydantic Evals report
JSON without sending report data to a server.

## Start the viewer

```bash
make eval-viewer
```

Open <http://127.0.0.1:8765>, then choose or drag one or more report files into
the page. Reports remain in browser memory and are not uploaded.

## Create a report

Use `--save-report` with an evaluation command:

```bash
make eval-retrieval \
  EVAL_FLAGS="--save-report eval-reports/retrieval.json"
```

The viewer shows:

- report and experiment metadata;
- case, pass, failure, assertion, and duration summaries;
- case-name and status filters;
- assertion results and judge reasons;
- metrics, scores, labels, and attributes;
- inputs, expected outputs, actual outputs, and case metadata;
- evaluator failures and raw case JSON.

Multiple files can be loaded and selected from the run list. Side-by-side or
baseline comparison is intentionally deferred to a later increment.

## Data sensitivity

Reports can contain prompts, answers, retrieved evidence, fixture paths, and
tool arguments. They are gitignored by default. Review report contents before
sharing them or enabling Logfire export.
