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

Every URL sent to `@WebIngest` is recorded under
`data/teams/<runtime-team-id>/urls.json`, separate from the knowledge graph itself.
Alongside submission history, it stores a normalized hash of the last successfully
ingested Tavily content. When a later fetch produces the same hash, `@WebIngest` skips
extraction and graph updates. Ask explicitly to **force re-ingestion** to bypass that
check. A new hash is committed only after the graph update succeeds, so a failed refresh
does not replace the last known successful state. The frontend shows the active team's
submitted URLs in the **Imported URLs** panel (fetched from `GET /api/urls`).

### Persistent teams

The backend persists team lifecycle state, events, and agent snapshots with
`TeamManager` and `YamlEventStore`. `data/active-team.json` records the selected runtime
UUID. A normal restart stops and resumes that same team, so its Qdrant-scoped knowledge
and imported URLs remain visible.

The **Teams** screen separates reusable catalog definitions from persisted runtime
instances. Select **Activate** to switch to an existing knowledge scope, or **Create
instance** to start a separate scope from a catalog definition. Only one instance is
active at a time, and the last active instance is loaded automatically after restart.

The **Settings** page reports whether the runtime uses persistent Qdrant or the
in-memory backend, whether the configured Qdrant endpoint is reachable, the
`knowledge_graph` collection state and point count, URL-ingestion counts, and an
operational synchronization assessment. It never returns credential values.

Each successful commit also records the entity names and relation triples attributed to
that URL. When changed content is ingested, `@WebIngest` updates retained facts, creates
new facts, and deletes stale facts owned exclusively by the previous version of that
source. Facts also claimed by another URL are not offered for deletion.

This is a hash of Tavily's query-filtered extracted text, not of the origin page bytes.
The Tavily request still happens, and a materially different extraction query or result
may cause reprocessing even when the underlying page did not change.

Do not reset only `data/teams/` or only Qdrant: that leaves team lifecycle, ingestion
history, and stored knowledge inconsistent. For the Docker stack, clear both named
volumes together:

```bash
make status        # inspect backend, Qdrant, URL counts, and synchronization
make reset-storage # stop the stack and delete both persistent data volumes
make reset-and-up  # reset both stores, then rebuild and start the stack
```

These reset commands are intentionally explicit and destructive. They remove all locally
persisted Qdrant graph data and imported-URL history for this Compose project. The
synchronization assessment is conservative: URL count and graph point count cannot be
equaled because one source may produce many entities and relations.

## Development

```bash
make lint        # ruff
make format      # ruff format
make typecheck   # mypy
make test        # pytest (team-boot + input parsing; no network/LLM required)
```

## Evaluations

The evaluation code is split between a reusable package and the
Knowledge Akgents integration:

- **`src/akgentic_evals/`** contains application-independent runtime,
  case-authoring, evidence, completion, deterministic-evaluator, dataset
  definition, judge-calibration, and report primitives.
- **`evals/`** contains Knowledge Akgents fixtures, team construction,
  datasets, accepted answer policy, retrieval-answer judges, and command-line
  runners.

`akgentic_evals` is currently shipped in the same wheel as
`knowledge_akgents`. It is an internal extraction, not yet a separately
published package. Its design still needs to be validated against a second
Akgentic application before that boundary should be considered stable.

The original design and recorded pilot results are in
[`evals-plan.md`](evals-plan.md). Contributor-oriented guides start at
[`docs/help.md`](docs/help.md).

### Where evaluation code lives

| Location | Responsibility |
|---|---|
| `src/akgentic_evals/adapters.py` | Translation from raw Akgentic and Pydantic AI events to normalized evaluation events |
| `src/akgentic_evals/models.py` | Normalized output records, composite `(run_id, tool_call_id)` invocation identity, correlated tool invocations, and successful-evidence selection |
| `src/akgentic_evals/events.py` | Transport-independent message, tool, evidence, usage, failure, and stop events |
| `src/akgentic_evals/collector.py` | Thread-safe conversion of normalized events into `AkgenticCaseOutput` |
| `src/akgentic_evals/completion.py` | Completion-policy protocol and sender/recipient-based response selection |
| `src/akgentic_evals/runtime.py` | Single-turn and multi-turn case authoring, runtime/factory protocols, capabilities, and lifecycle execution |
| `src/akgentic_evals/evaluators.py` | Generic completion, response-text, route, actor, tool, evidence, count, and usage evaluators |
| `src/akgentic_evals/diagnostics.py` | Generic normalized-output and span inventory evaluators |
| `src/akgentic_evals/datasets.py` | Strict evaluator definitions, builders, dataset composition, and named-case selection |
| `src/akgentic_evals/calibration.py` | Shared evidence-judge input construction, calibration input, and human-label agreement summaries |
| `src/akgentic_evals/reporting.py` | Native Pydantic Evals report persistence |
| `evals/harness/models.py` | `KnowledgeCaseInput` and its nested `KnowledgeEvaluationEnvironment` |
| `evals/harness/runtime.py` | `KnowledgeRuntimeFactory`, Knowledge fixture composition, and the `KnowledgeTeam` runtime adapter |
| `evals/harness/running_system.py` | WebSocket runtime for an already-running backend and its weaker capability declaration |
| `evals/harness/catalog.py` | Production/evaluation catalog selection and strict tool replacement |
| `evals/harness/dataset_loader.py` | Knowledge dataset schema, fixture selection, shared retrieval contract, and conversion to Pydantic Evals |
| `evals/evaluators/retrieval.py` | Knowledge-specific groundedness and answer-relevance judges for retrieval answers |
| `evals/scenarios/` | Python-defined stateful, multi-turn, and failure scenarios |
| `evals/datasets/` | Declarative JSON retrieval cases and their schema |
| `evals/examples/` | Copyable application-owned examples, including the RAG4j running-system dataset |
| `evals/runners/` | CLI entry points, report metadata, and experiment execution |

The two execution paths converge before evidence is evaluated:

```text
Local case
  KnowledgeCaseInput -> KnowledgeRuntimeFactory -> KnowledgeTeamRuntime
                -> AkgenticEventAdapter -> normalized events

Running backend
  AkgenticCaseInput -> RunningSystemRuntime
                -> WebSocket payload decoder
                -> normalized events

Both
  normalized events -> EvaluationEventCollector -> AkgenticCaseOutput
                    -> generic + application-specific evaluators
                    -> Pydantic Evals report
```

Use these ownership rules when adding code:

- Put transport-independent case authoring, evidence, lifecycle, completion,
  evaluator definitions, diagnostics, dataset composition, judge-input
  construction, calibration calculations, or report persistence in
  `src/akgentic_evals/`.
- Put reusable Akgentic/Pydantic AI event decoding in
  `src/akgentic_evals/adapters.py`.
- Put Knowledge team construction, catalogs, fixture tools, and persistent
  runtime access in `evals/harness/`.
- Put Knowledge evaluation environments, expected routes, domain facts,
  accepted terms, and judge rubrics in `evals/`, because those values define
  this application's behavior.
- Do not add Knowledge-specific actor names, tool names, or answer vocabulary
  to `src/akgentic_evals/`.

`KnowledgeCaseInput` extends the generic `AkgenticCaseInput` with one nested
`KnowledgeEvaluationEnvironment`. The generic input owns `message`, `target`,
ordered `turns`, timeout validation, and `ordered_turns()`. The environment
owns fixture URLs, fixture files, simulated web failures, and fixture
knowledge. The runtime factory receives the complete application input, while
`akgentic_evals` treats the additional configuration as opaque.

### Runtime guarantees

Both runtimes implement `AkgenticEvalRuntime`, but they do not provide the
same guarantees. The runner stores these capabilities in report metadata.

| Capability | Isolated `KnowledgeTeamRuntime` | `RunningSystemRuntime` |
|---|---:|---:|
| Request correlation | Yes | No |
| Isolated execution | Yes | No |
| Trace context | Yes | No |
| Actor quiescence detection | No | No |

The running backend broadcasts WebSocket events and does not attach an
evaluation case or turn ID. Run those datasets serially and avoid other active
clients, but do not interpret that precaution as strong isolation.

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

Run any self-contained retrieval dataset definition without adding Python:

```bash
make eval-dataset DATASET=evals/datasets/retrieval_only.json
```

To evaluate facts already ingested into the configured production Qdrant
collection, use a JSON dataset with
`"knowledge": {"source": "running_system"}`:

```bash
make eval-live-dataset \
  DATASET=evals/examples/rag4j/dataset.json \
  EVAL_FLAGS="--save-report eval-reports/rag4j-documentation.json"
```

This sends cases through the already-running production application and its
real `search_graph` tool. It does not ingest the page; populate Qdrant first.
The example folder explains which parts to copy and replace for another
application-owned source.

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

`eval-reports/` contains selected reports used as article evidence and
regression references. Reports can include prompts, answers, and tool
arguments, so inspect new reports before committing them rather than treating
the directory as safe for arbitrary raw output.

No GitHub Actions workflow is provided yet. The project currently resolves
`akgentic-llm` from the editable sibling path `../akgentic-llm`, which a generic
hosted runner does not have. CI should hard-gate `make test-evals` only after
that dependency is available through a package registry or an explicit checkout
step. Paid evaluations and subjective judge scores should remain manual or
scheduled, not run on every pull request.

## Project layout

```
src/knowledge_akgents/   settings, catalog loading, events bridge, persistent team runtime,
                         FastAPI app, and team-scoped imported URL tracking
src/akgentic_evals/      reusable adapters, case authoring, normalized evidence, runtime
                         factories, completion, evaluators, dataset definitions, calibration,
                         and reports
config/catalog/          production and evaluation akgentic-catalog namespaces
evals/harness/           Knowledge runtime configuration, fixtures, catalog composition,
                         and application dataset loading
evals/evaluators/        Knowledge-specific retrieval-answer judges
evals/datasets/          JSON case definitions, schema, and authoring README
evals/examples/          copyable application-owned evaluation examples
evals/fixtures/          controlled web-page content for specialized scenarios
evals/scenarios/         Python orchestration for multi-turn and failure scenarios
evals/routes.py          shared Knowledge actor-route policy
evals/runners/           command-line experiment entry points and CLI helpers
eval-reports/            reviewed native Pydantic Evals reports retained as evidence
eval-viewer/             local static viewer for saved evaluation reports
docs/                    contributor help organized by topic
frontend/                static Human-Proxy UI + nginx config
docker/                  backend & web Dockerfiles
compose.yaml             qdrant + backend + web
data/                    local cache (imported-URL history); gitignored, safe to delete
```

## License

AGPL-3.0-only (the akgentic packages this depends on are AGPL-3.0).
