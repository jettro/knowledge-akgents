# Adding evaluation cases

## Add a retrieval case

For the current Python-based dataset, add a case to
`evals/datasets/retrieval_only.py`:

```python
_case(
    "jane-role",
    "What role does Jane Doe have?",
    ("software engineer",),
    fixture_path,
    timeout_seconds,
    "canonical",
)
```

The shared retrieval dataset already checks that:

- the team completes with a human response;
- the expected actor route is followed;
- `search_graph` is called successfully;
- ingestion and graph-update tools are not called.

The tuple of required terms is a small deterministic contract for the answer.
Add a paraphrase as a separate case when different wording should produce the
same result.

## Add fixture knowledge

Add reviewed records to `evals/fixtures/pilot_knowledge.json`, or introduce a
separate fixture when the cases represent another knowledge domain. Keep
fixtures small enough to review manually and record where and when the source
was captured in case metadata.

Do not put secrets, production customer data, or access tokens in fixtures.

## Add case-specific expectations

Attach evaluators directly to a `Case` when it has requirements that do not
apply to the whole dataset. The missing-fact regression, for example, checks
that the response acknowledges unavailable knowledge, recommends ingestion,
and makes no more than two searches.

Reuse evaluators from `evals/event_evaluators.py`. Add a new evaluator only
when the required behavior cannot be expressed by the existing ones.

## Validate the case

Run the harness tests first:

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

## Planned YAML migration

The intended end state is for ordinary case contributions to be YAML rather
than Python. A future case could look like:

```yaml
name: jane-role
question: What role does Jane Doe have?
fixture: jane.json
variant: canonical
expect:
  answer_contains:
    - software engineer
  required_tools:
    - search_graph
  forbidden_tools:
    - web_fetch_tool
    - update_graph
```

A Pydantic model will validate this schema, and a Python loader will translate
it into Pydantic Evals `Case` objects. Evaluators and task execution will remain
in Python.

This migration is intentionally deferred until the case vocabulary is stable.
It should make contributions easier without hiding unsupported behavior behind
free-form YAML.
