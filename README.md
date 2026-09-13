# Knowledge Akgents

A sample application on the [akgentic framework](https://github.com/b12consulting/akgentic-framework):
a **web Human Proxy** talks to an **Akgentic team** that can

- **query a knowledge base** (the Knowledge agent), and
- **ingest knowledge from a web page** into that same base (the Web-Ingest agent),

with **Qdrant** as the vector store. Deployed with Docker; managed with `uv`; common tasks via `make`.

> Uses released akgentic modules, plus **local editable** `../akgentic-tool` and `../akgentic-llm`.
> See `plan.md` for the full design and the decisions behind it.

## Architecture

```
Browser (Human Proxy UI)  ──ws──►  FastAPI backend  ──►  Akgentic actor team
     nginx :8080                       :8000               @Manager → @Knowledge / @WebIngest
                                                                 │
                                                           #VectorStore ──► Qdrant :6333
```

- **`@Manager`** routes the human's request to a specialist.
- **`@Knowledge`** answers using the `KnowledgeGraphTool` (search) over the shared `#VectorStore`.
- **`@WebIngest`** fetches a page (`SearchTool`/Tavily), extracts entities+relations, and writes them
  via the `KnowledgeGraphTool` (update) into the **same** store — so what it ingests is queryable.

## Prerequisites

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Docker.
- The sibling checkouts `../akgentic-tool` and `../akgentic-llm` next to this project.
- A `.env` (copy `.env.example`) with:
  - `OPENAI_API_KEY` (and `OPENAI_BASE_URL` if `gpt-5.6-luna` is behind a gateway),
  - `TAVILY_API_KEY` (for web fetch/crawl),
  - `AKGENTIC_QDRANT_URL` (local dev only; compose sets it automatically).

## Run with Docker (full stack)

```bash
cp .env.example .env   # fill in the keys
make up                # qdrant + backend + web
# open http://localhost:8080
make logs              # tail backend
make down
```

## Run locally (dev)

```bash
make sync                                   # install deps (incl. local tool & llm)
docker run -p 6333:6333 qdrant/qdrant       # or leave AKGENTIC_QDRANT_URL unset for in-memory
make run                                     # backend on :8000
make web                                     # static UI on :8080
# open http://localhost:8080/?backend=localhost:8000
```

## Using it

- Type a question → routed to `@Manager`, which delegates to `@Knowledge`.
- Paste a URL in the **Ingest URL** box → routed to `@WebIngest` to fetch, extract, and store.
- Route directly by prefixing a message with `@Knowledge` or `@WebIngest`.

### Imported URLs

Every URL sent to `@WebIngest` is recorded in a small local cache — `data/urls.json` —
separate from the knowledge graph itself. Alongside submission history, it stores a
normalized hash of the last successfully ingested Tavily content. When a later fetch
produces the same hash, `@WebIngest` skips extraction and graph updates. Ask explicitly to
**force re-ingestion** to bypass that check. A new hash is committed only after the graph
update succeeds, so a failed refresh does not replace the last known successful state.
The frontend shows the submitted URLs in the **Imported URLs** panel (fetched from
`GET /api/urls`).

Each successful commit also records the entity names and relation triples attributed to
that URL. When changed content is ingested, `@WebIngest` updates retained facts, creates
new facts, and deletes stale facts owned exclusively by the previous version of that
source. Facts also claimed by another URL are not offered for deletion.

This is a hash of Tavily's query-filtered extracted text, not of the origin page bytes.
The Tavily request still happens, and a materially different extraction query or result
may cause reprocessing even when the underlying page did not change.

To start over, delete the `data/` directory (or just `data/urls.json`) and restart the
backend — this only clears the URL history, not the knowledge base itself (that lives in
Qdrant, or in memory if `AKGENTIC_QDRANT_URL` isn't set).

## Development

```bash
make lint        # ruff
make format      # ruff format
make typecheck   # mypy
make test        # pytest (team-boot + input parsing; no network/LLM required)
```

## Evaluations

The Pydantic Evals harness lives in `evals/`; its design and recorded pilot
results are in [`evals-plan.md`](evals-plan.md). Contributor-oriented guides
start at [`docs/help.md`](docs/help.md).

Run the deterministic harness tests without network or model calls:

```bash
make test-evals
```

Live evaluation targets use reviewed local fixtures and force the knowledge
store to be in-memory. They require `OPENAI_API_KEY` and make paid model calls,
but do not use Tavily or export to Logfire by default:

```bash
make eval-ingestion        # one Jettro ingestion case
make eval-jettro           # Jettro ingest + two retrieval turns
make eval-yuma             # Yuma ingest + two retrieval turns
make eval-prompt-injection # synthetic untrusted-page ingestion scenario
make eval-no-useful-content # synthetic boilerplate-only ingestion scenario
make eval-unreachable-url  # controlled web-fetch failure scenario
make eval-routing          # manager and direct-specialist routing cases
make eval-change-aware-ingestion # unchanged, forced, and changed ingestion cases
make eval-retrieval        # thirteen retrieval, conflict, and missing-knowledge cases
make eval-variance         # retrieval cases repeated three times
make eval-judge            # static two-dimensional judge calibration
make eval-judge-stability  # judge calibration repeated three times
```

Run any self-contained retrieval fixture dataset without adding Python:

```bash
make eval-fixture FIXTURE_DATASET=evals/fixtures/retrieval_only.json
```

Three additional targets load the exact production catalog team. They keep
Qdrant and URL-ingestion state isolated, but use the production web tool and
therefore make real Tavily calls as well as paid model calls:

```bash
make eval-production-ingestion # live Jettro ingestion
make eval-production-jettro    # live Jettro ingest + retrieval
make eval-production-yuma      # live Yuma ingest + retrieval
```

Run both end-to-end cases and export them into one report:

```bash
make eval-production-e2e
# writes eval-reports/production-e2e.json
```

Override the output path when needed:

```bash
make eval-production-e2e EVAL_REPORT=eval-reports/production-e2e-2026-09-13.json
```

These targets do not use production Qdrant merely because they load the
production namespace. They explicitly clear `AKGENTIC_QDRANT_URL`, use a
temporary URL repository per case, and leave Logfire export disabled unless
requested. Persistent Qdrant requires bypassing the Make target and passing
both a configured URL and `--allow-persistent-store`.

Pass additional runner options through `EVAL_FLAGS`; Logfire export is always
explicit:

```bash
make eval-retrieval EVAL_FLAGS=--send-to-logfire
make eval-retrieval EVAL_TIMEOUT=240
make eval-retrieval EVAL_FLAGS="--case jettro-unknown-favorite-database"
make eval-retrieval EVAL_FLAGS="--case jettro-profession --with-judges"
```

`--with-judges` adds two paid evaluator calls per case. The calibrated judges
assess groundedness and answer relevance against the actual successful
`search_graph` content captured from the agent run.

Save a native Pydantic Evals report and compare a later candidate run against
it:

```bash
make eval-retrieval EVAL_FLAGS="--save-report eval-reports/retrieval-baseline.json"
make eval-retrieval EVAL_FLAGS="--baseline eval-reports/retrieval-baseline.json"
```

Inspect one or more saved reports in the local web viewer:

```bash
make eval-viewer
# open http://127.0.0.1:8765
```

The viewer reads selected files locally in the browser. See
[`docs/evaluation-report-viewer/help.md`](docs/evaluation-report-viewer/help.md)
for its available views and data-sensitivity notes.

`eval-reports/` is gitignored because reports can contain prompts, answers, and
tool arguments. Commit curated conclusions or thresholds instead of raw
execution data.

No GitHub Actions workflow is provided yet. The project currently resolves
`akgentic-llm` from the editable sibling path `../akgentic-llm`, which a generic
hosted runner does not have. CI should hard-gate `make test-evals` only after
that dependency is available through a package registry or an explicit checkout
step. Paid evaluations and subjective judge scores should remain manual or
scheduled, not run on every pull request.

## Project layout

```
src/knowledge_akgents/   settings, catalog loading, events bridge, team runtime, FastAPI app
                         (repository.py tracks imported URLs in data/urls.json)
config/catalog/          production and evaluation akgentic-catalog namespaces
evals/                   Pydantic Evals JSON fixture datasets, evaluators, and runners
eval-viewer/             local static viewer for saved evaluation reports
docs/                    contributor help organized by topic
frontend/                static Human-Proxy UI + nginx config
docker/                  backend & web Dockerfiles
compose.yaml             qdrant + backend + web
data/                    local cache (imported-URL history); gitignored, safe to delete
```

## License

AGPL-3.0-only (the akgentic packages this depends on are AGPL-3.0).
