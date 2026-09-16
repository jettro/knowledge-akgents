# RAG4j running-system evaluation example

This folder is a copyable example of an application-owned evaluation dataset.
It asks questions about the RAG4j/p documentation that has already been
ingested into a running Knowledge Akgents application.

The example deliberately contains only application policy:

- the source whose ingestion is being accepted;
- questions and metadata;
- expected evidence and answer terms;
- accepted wording for a fact that is not present.

The reusable JSON evaluator definitions live in `src/akgentic_evals/`.
Knowledge-specific validation and conversion live in
`evals/harness/dataset_loader.py`. The shared JSON Schema remains in
`evals/datasets/schema.json`.

## Prerequisite

Start Knowledge Akgents and ingest:

```text
https://rag4j.org/documentation/
```

The running-system evaluation reads the existing application knowledge. It
does not ingest or replace data.

## Run the example

```bash
make eval-live-dataset \
  DATASET=evals/examples/rag4j/dataset.json \
  EVAL_FLAGS="--save-report eval-reports/rag4j-documentation.json"
```

## Create another application-owned example

1. Copy this folder and rename it for the source or feature being evaluated.
2. Change the dataset `name`, source metadata, questions, and evaluator terms.
3. Keep `knowledge.source` set to `running_system` for knowledge already owned
   by the application.
4. Point `$schema` at `evals/datasets/schema.json` relative to the copied file.
5. Run it with `make eval-live-dataset DATASET=<path-to-dataset.json>`.

Use `knowledge.source: fixtures` instead when the dataset should supply
controlled records and run against an isolated local evaluation team.
