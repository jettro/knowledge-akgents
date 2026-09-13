# Adding evaluation cases

## Add a retrieval case

Add ordinary retrieval cases to `evals/cases/retrieval_only.yaml`:

```yaml
- name: jane-role
  message: What role does Jane Doe have?
  metadata:
    prompt_variant: canonical
  evaluators:
    - type: human_response_contains_terms
      required_terms: [software engineer]
```

The shared retrieval dataset already checks that:

- the team completes with a human response;
- the expected actor route is followed;
- `search_graph` is called successfully;
- ingestion and graph-update tools are not called.

The required terms are a small deterministic contract for the answer.
Add a paraphrase as a separate case when different wording should produce the
same result.

The YAML file is validated strictly. Unknown fields, unknown evaluator types,
duplicate case names, missing vocabulary references, invalid call-count ranges,
absolute fixture paths, and fixture paths outside `evals/` are rejected.

## Add fixture knowledge

`default_fixture` applies to every case that does not define its own `fixture`.
Paths are relative to the YAML file and must remain inside `evals/`.

Add reviewed records to `evals/fixtures/pilot_knowledge.json`, or introduce a
separate fixture when the cases represent another knowledge domain. Keep
fixtures small enough to review manually and record where and when the source
was captured in case metadata.

Do not put secrets, production customer data, or access tokens in fixtures.

## Add case-specific expectations

Add case-specific evaluator definitions under the case's `evaluators` key when
requirements do not apply to the whole dataset. The supported YAML evaluator
types are currently:

- `human_response_contains_terms`;
- `human_response_contains_any_term`;
- `tool_call_count`.

Reusable alternative wording can be defined once under the top-level
`vocabularies` mapping and referenced with `accepted_terms_ref`. The
missing-knowledge cases use this mechanism.

Shared routing, required-tool, forbidden-tool, completion, and successful-return
contracts intentionally remain in `evals/datasets/retrieval_only.py`. They are
evaluation logic, not case data.

When a requirement cannot be represented by the allow-listed YAML vocabulary,
add or reuse a Python evaluator in `evals/event_evaluators.py`, define its
strict configuration model in `evals/yaml_cases.py`, and add loader rejection
tests. YAML must never contain arbitrary Python or evaluator expressions.

## Validate the case

Run the schema and deterministic harness tests first:

```bash
make test-evals
```

Then run only the new live case:

```bash
make eval-retrieval EVAL_FLAGS="--case jane-role"
```

Add `--with-judges` only when groundedness and semantic relevance need to be
checked:

```bash
make eval-retrieval EVAL_FLAGS="--case jane-role --with-judges"
```

Live runs require credentials and make paid model calls.
