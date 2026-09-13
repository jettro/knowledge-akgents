# Adding fixture datasets

Ordinary retrieval datasets are self-contained JSON files under
`evals/fixtures/`. A bundle contains:

- one or more named knowledge fixtures;
- questions and case metadata;
- reusable vocabularies;
- allow-listed evaluator settings.

No Python module or scenario registration is required.

## Create a dataset

Create a file such as `evals/fixtures/people.json`:

```json
{
  "version": 1,
  "task": "retrieval",
  "name": "knowledge-akgents/people",
  "default_fixture": "people",
  "default_metadata": {
    "source": "reviewed-example"
  },
  "vocabularies": {},
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
  },
  "cases": [
    {
      "name": "jane-role",
      "message": "What role does Jane Doe have?",
      "metadata": {
        "prompt_variant": "canonical"
      },
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

`default_fixture` names the fixture used by cases that omit `fixture`. A case
can select another fixture declared in the same file:

```json
{
  "name": "conflicting-answer",
  "message": "Which database does Alex prefer?",
  "fixture": "conflicting-database",
  "evaluators": []
}
```

This keeps cases and the exact knowledge they use in one reviewable artifact.
There are no fixture paths to resolve and no external files that can silently
drift away from the dataset.

## Available evaluator settings

Case-level evaluators currently support:

- `human_response_contains_terms`;
- `human_response_contains_any_term`;
- `tool_call_count`.

Reusable alternative wording can be declared under `vocabularies` and selected
with `accepted_terms_ref`.

Every retrieval fixture dataset automatically checks that:

- the team completes with a human response;
- the expected Manager-to-Knowledge route is followed;
- `search_graph` is called successfully;
- web ingestion and graph updates are not called.

The JSON is validated strictly with Pydantic. Unknown fields, unknown evaluator
types, duplicate case names, missing fixture names, missing vocabulary
references, invalid records, and invalid call-count ranges are rejected.
Arbitrary Python and evaluator expressions are never loaded from the file.

## Run the dataset

Run any fixture bundle with:

```bash
make eval-fixture FIXTURE_DATASET=evals/fixtures/people.json
```

Select one case or save a report through `EVAL_FLAGS`:

```bash
make eval-fixture \
  FIXTURE_DATASET=evals/fixtures/people.json \
  EVAL_FLAGS="--case jane-role --save-report eval-reports/people.json"
```

The existing retrieval target is the same generic runner with
`evals/fixtures/retrieval_only.json` selected:

```bash
make eval-retrieval
```

Live runs require credentials and make paid model calls. Run `make test-evals`
first to validate fixture files and harness behavior without network or model
calls.

When a requirement cannot be represented by the allow-listed JSON vocabulary,
add or reuse a Python evaluator in `evals/event_evaluators.py`, extend its
strict definition in `evals/fixture_datasets.py`, and add loader rejection
tests.
