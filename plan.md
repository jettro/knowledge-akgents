# Knowledge Akgents — Project Plan

A sample application built on the [akgentic framework](https://github.com/b12consulting/akgentic-framework)
that pairs a **web-based Human Proxy** with an **Akgentic team** capable of (1) answering
questions from a knowledge base and (2) ingesting knowledge from arbitrary web pages into
that same knowledge base. Storage is a **Qdrant** vector database. Everything is deployed
with **Docker**, the project is managed with **uv**, and common tasks run through a **Makefile**.

> Status: **PLAN — not yet implemented.** Nothing below is built yet; this document is for us
> to agree on before writing code.

---

## 1. Goals

1. A **web client** that acts as the `HumanProxy` — the human talks to the team from a browser.
2. An Akgentic **team** with:
   - a **Knowledge agent** that queries the knowledge base via the vector-store-backed tool, and
   - a **Web-ingest agent** that fetches a web page, extracts knowledge, and writes it back
     through the **same** vector store.
3. Use **released** versions of every akgentic module **except `akgentic-tool`**, which is
   consumed from the local checkout at `../akgentic-tool` (currently `v1.7.0`).
4. **uv** for project/dependency management, a **Makefile** for the common uv tasks.
5. **Docker** deployment: a website container, a backend container hosting the team, and a
   Qdrant container for storage.

---

## 2. How this maps onto the akgentic framework

Key finding from reading the framework and the local `akgentic-tool`:

- **`VectorStoreTool` exposes no LLM tools.** It is only a *config card* that guarantees the
  `VectorStoreActor` singleton (`#VectorStore`) exists and picks the backend. Backend selection
  is environment-driven: exporting **`AKGENTIC_QDRANT_URL`** makes `qdrant` the default backend
  (see `akgentic/tool/vector_store/qdrant.py`).
- The agent-facing "knowledge base" is realised by a **consumer** of the vector store. The natural
  fit shipped with the tool is **`KnowledgeGraphTool`**, which `depends_on: ["VectorStoreTool"]`
  and exposes real LLM tools:
  - `search_graph(SearchQuery)` — semantic/hybrid **query** of the knowledge base,
  - `update_graph(ManageGraph)` — **store** entities/relations (embedded into the same Qdrant
    collection via the shared `#VectorStore` actor).
- **Web retrieval/extraction** is provided by **`SearchTool`** (Tavily), specifically its
  `web_fetch`/`web_crawl` capabilities that extract page content with a relevance query.

So the requested behaviour is achieved by giving the two agents the right tool cards, all pointed
at the **same** `#VectorStore` singleton and the same `knowledge_graph` collection.

> **Decision (A):** the knowledge base is represented as a **KnowledgeGraph** (entities + relations,
> hybrid search) via `KnowledgeGraphTool` — the ready-made vector-store consumer in `akgentic-tool`.
> (The alternative — a plain "chunk → embed → similarity search" RAG store — would need a custom
> `ToolCard` over the `VectorStoreActor` protocol; not pursued.)

---

## 3. Team & agent design

Actor wiring follows the framework's `src/agent_team/main.py` pattern (ActorSystem → Orchestrator →
register `AgentCard`s → `HumanProxy` → agents), but driven by a web backend instead of a CLI loop.

| Actor | Role | Tools | Purpose |
|---|---|---|---|
| `@Human` | `HumanProxy` | — | Bridge between the browser and the team (see §4). |
| `@Manager` | Manager/router | none (or read-only) | Receives human messages, routes to the right specialist. `routes_to = [Knowledge, WebIngest]`. |
| `@Knowledge` | Knowledge agent | `VectorStoreTool`, `KnowledgeGraphTool` (search) | Answers questions by querying the knowledge base. |
| `@WebIngest` | Web-ingest agent | `VectorStoreTool`, `SearchTool` (web_fetch/crawl), `KnowledgeGraphTool` (update) | Fetches a page, extracts knowledge, stores it in the shared store. |

Notes:
- The **`@Manager`** is a thin coordinator so the human can send plain messages and let the team
  route; direct `@Knowledge` / `@WebIngest` addressing still works. *(Decision B: keep the lightweight
  Manager.)*
- Both specialists include `VectorStoreTool()` and `KnowledgeGraphTool(...)` with the **same**
  `vector_store_name` (`#VectorStore`) and collection, so ingestion and querying hit the same data.
- Models: `ModelConfig(provider="openai", model="gpt-5.6-luna")`. `gpt-5.6-luna` is reached through an
  **OpenAI-compatible endpoint** — you provide a **`.env`** with `OPENAI_API_KEY` (and, if the model
  lives behind a gateway, `OPENAI_BASE_URL`). The local `akgentic-llm 2.2.0` carries the newer
  provider/cost roster (see §5). Embeddings use `text-embedding-3-small` (1536 dims) — the
  `KnowledgeGraphTool` collection dimension must match. *Assumption: the embedding model is served by
  the same OpenAI credentials/endpoint as the chat model unless you tell us otherwise.*

Tool cards (in `tools.py`), mirroring `akgentic-framework/src/agent_team/tools.py`:

```python
vector_store_tool = VectorStoreTool()  # backend = qdrant via env
kg_search_tool = KnowledgeGraphTool(search=True, update_graph=False)
kg_ingest_tool = KnowledgeGraphTool(update_graph=True, search=True)
web_tool = SearchTool(
    web_fetch=WebFetch(timeout=30), web_crawl=WebCrawl(timeout=150, max_depth=2, limit=10)
)
```

---

## Licensing (AGPL-3.0) — the real constraint, not "enterprise"

Everything we depend on is **AGPL-3.0-only**: `akgentic-core`, `akgentic-llm`, `akgentic-tool`,
`akgentic-infra` (community tier), and the Angular `akgentic-frontend`.

- **There is no separate/commercial license blocking the community infra or the Angular UI.** The
  "enterprise" concern is a *packaging* distinction, not a license one: the enterprise (K8s/Dapr) and
  department (Docker Compose) tiers ship as **separate packages** — `akgentic-infra-enterprise` and
  `akgentic-infra-department`. We depend only on **`akgentic-infra`** = the community, single-process
  tier (NoAuth, `YamlEventStore`, local filesystem). We never install the enterprise/department
  packages, so there is no enterprise version in the build.
- **The Angular frontend adds no new license type** — it is AGPL like the rest. So "infra + Angular"
  is not a *different* license problem; it is the same AGPL question as the backend.
- **AGPL copyleft is the thing to decide on.** Our **backend imports AGPL akgentic packages**, so the
  backend is subject to AGPL §13 (network copyleft) regardless of the frontend: if we make the service
  available to third parties over a network, we must offer the complete corresponding source of the
  AGPL parts and their derivatives under AGPL. For an internal/sample app this is normally fine.
  - A **custom frontend** that only talks HTTP/WebSocket to the backend is a separate program (not a
    derivative), so it does not inherit AGPL from the backend — maximum freedom for the UI code.
  - Reusing the **Angular `akgentic-frontend`** is simplest and is the same AGPL license we already
    accept for the backend.

> Net: neither option introduces a *new* or *enterprise* license. The only decision is whether we are
> comfortable being AGPL for the backend (unavoidable once we import these packages) and, separately,
> whether we want the frontend to also be AGPL (Angular) or license-independent (custom UI).

---

## 4. Web client (Human Proxy) ↔ backend

- **Backend** (`FastAPI` + `uvicorn`): on startup boots the ActorSystem, Orchestrator, registers the
  agent cards, creates the `HumanProxy` and the team. It exposes:
  - `GET /` health/info,
  - `GET /api/team` roster,
  - `WS /ws/chat` — the browser sends user messages; the backend calls `human_proxy.send(...)` and
    streams agent traffic back. An `EventSubscriber` (like `MessagePrinter` in the example) captures
    `SentMessage` / `ToolCallEvent` and forwards them to the websocket as JSON so the UI can show the
    live conversation and tool calls.
- **Frontend** (the "Human Proxy web client"): a small single-page app (plain HTML/CSS/vanilla JS —
  no heavy framework needed for a sample) that opens the websocket, renders the chat, lets the user
  `@mention` agents, and has a shortcut to "ingest a URL" (sends a message to `@WebIngest`).
  Served as static files by **nginx**.

**Decision (C — resolved): custom lightweight FastAPI backend + static JS frontend.** Self-contained,
no Node/Angular toolchain, full control of the UI, and the custom UI stays outside AGPL copyleft. We do
**not** reuse the Angular frontend, and we **drop `akgentic-infra`** entirely — the custom backend
boots the actor system directly (see §5, Decision K).

---

## 5. Dependency strategy (latest releases + local `akgentic-tool` **and** local `akgentic-llm`)

You want the **latest** versions. The `akgentic-framework` meta-package **hard-pins its whole closure
with `==`** (and its "source mode" keeps those pins even for local checkouts), which conflicts with
our two local, ahead-of-release packages. So we **skip the meta-package** and depend on the individual
akgentic packages, letting uv resolve the latest compatible release for the ones we don't override,
and pointing the two local ones at their checkouts:

- **`akgentic-tool`** → local `../akgentic-tool` (currently `v1.7.0`, editable)
- **`akgentic-llm`** → local `../akgentic-llm` (currently `v2.2.0`, editable) — you keep it up to date

`pyproject.toml` (sketch):

```toml
[project]
name = "knowledge-akgents"
requires-python = ">=3.12"
dependencies = [
    "akgentic-core",                              # latest release
    "akgentic-llm",                               # local editable (see sources)
    "akgentic-agent",                             # latest release
    "akgentic-team",                              # latest release
    "akgentic-tool[qdrant,vector_search,docs]",   # local editable (see sources)
    "fastapi",
    "uvicorn[standard]",
    "websockets",
    "pydantic-settings",
]

[dependency-groups]
dev = ["ruff", "mypy", "pytest", "pytest-asyncio"]

[tool.uv.sources]
akgentic-tool = { path = "../akgentic-tool", editable = true }
akgentic-llm  = { path = "../akgentic-llm",  editable = true }
```

Notes / risks:
- **No `akgentic-infra`:** the custom FastAPI backend boots the actor system directly (ActorSystem →
  Orchestrator → agents → HumanProxy), so we **drop the `akgentic-infra` dependency** entirely —
  fewer moving parts, no `starlette<1.1` pin, and a smaller AGPL surface.
- **`akgentic-llm` local (`v2.2.0`):** carries the newer provider/cost roster, which is what we want
  for `gpt-5.6-luna`. It must not import the other akgentic packages (documented module boundary), so
  a local editable checkout is low-risk for the rest of the resolution.
- **Version-compatibility:** local `akgentic-tool 1.7.0` needs `akgentic-core>=1.5.13`; local
  `akgentic-llm 2.2.0` needs `akgentic-core>=1.5.0`. The latest releases of core/agent/team should
  satisfy both; we confirm with a post-`uv sync` smoke import and, if a conflict appears, pin the
  siblings to a compatible train.
- **Config/secrets** via `.env` (you provide it) + `pydantic-settings`: `OPENAI_API_KEY`,
  `OPENAI_BASE_URL` (gateway serving `gpt-5.6-luna`), `TAVILY_API_KEY`, `AKGENTIC_QDRANT_URL`,
  optional `AKGENTIC_QDRANT_API_KEY`.

---

## 6. Project layout

```
knowledge-akgents/
├── pyproject.toml                # uv-managed; [tool.uv.sources] -> local akgentic-tool
├── uv.lock
├── Makefile
├── .env.example                  # OPENAI_API_KEY, TAVILY_API_KEY, AKGENTIC_QDRANT_URL
├── plan.md
├── README.md
├── compose.yaml                  # qdrant + backend + web
├── src/
│   └── knowledge_akgents/
│       ├── __init__.py
│       ├── settings.py           # pydantic-settings
│       ├── tools.py              # VectorStoreTool / KnowledgeGraphTool / SearchTool cards
│       ├── agents.py             # AgentCards: Manager, Knowledge, WebIngest
│       ├── team.py               # ActorSystem + Orchestrator + HumanProxy wiring
│       ├── events.py             # EventSubscriber -> websocket bridge
│       └── app.py                # FastAPI app: /ws/chat, /api/team, lifespan boots team
├── frontend/
│   ├── index.html                # chat UI + "ingest URL" action
│   ├── app.js                    # websocket client
│   ├── styles.css
│   └── nginx.conf                # serves static + proxies /ws + /api to backend
├── docker/
│   ├── backend.Dockerfile        # uv-based image running uvicorn
│   └── web.Dockerfile            # nginx + static frontend
└── tests/
    ├── test_team.py              # team boots, roster correct
    └── test_ingest_query.py      # ingest a page -> query returns it (Qdrant via testcontainer/local)
```

---

## 7. Docker deployment

`compose.yaml` services:

1. **`qdrant`** — image `qdrant/qdrant:latest`, ports `6333/6334`, named volume `qdrant_data`
   for persistence.
2. **`backend`** — built from `docker/backend.Dockerfile` (uv install of this project incl. the
   local `akgentic-tool` copied into the build context). Env: `OPENAI_API_KEY`, `TAVILY_API_KEY`,
   `AKGENTIC_QDRANT_URL=http://qdrant:6333`. Runs `uvicorn knowledge_akgents.app:app`. Depends on
   `qdrant`.
3. **`web`** — built from `docker/web.Dockerfile` (nginx serving `frontend/`, proxying `/api` and
   `/ws` to `backend`). Published on `:8080`.

Build-context note: because both `akgentic-tool` and `akgentic-llm` live **outside** this project
directory (`../`), the backend image build uses **`build.context: ..`** (the parent `akgents/` dir)
with `dockerfile: knowledge-akgents/docker/backend.Dockerfile`, so the Dockerfile can `COPY`
`akgentic-tool/`, `akgentic-llm/`, and `knowledge-akgents/`, and `uv sync` resolves the local editable
sources.

---

## 8. Makefile targets (uv tasks)

| Target | Command | Purpose |
|---|---|---|
| `make sync` | `uv sync` | Install/resolve deps (incl. local tool, dev group). |
| `make run` | `uv run uvicorn knowledge_akgents.app:app --reload` | Run backend locally. |
| `make web` | `uv run python -m http.server -d frontend 8080` (dev) | Serve frontend locally. |
| `make lint` | `uv run ruff check .` | Lint. |
| `make format` | `uv run ruff format .` | Format. |
| `make typecheck` | `uv run mypy src` | Type check. |
| `make test` | `uv run pytest` | Tests. |
| `make up` / `make down` | `docker compose up -d --build` / `down` | Full stack via Docker. |
| `make logs` | `docker compose logs -f backend` | Tail backend logs. |
| `make clean` | remove `.venv`, caches | Housekeeping. |

---

## 9. Environment / secrets

`.env.example`:

```
OPENAI_API_KEY=            # LLM (gpt-5.6-luna via gateway) + embeddings (text-embedding-3-small)
OPENAI_BASE_URL=           # OpenAI-compatible gateway that serves gpt-5.6-luna
TAVILY_API_KEY=            # web_fetch / web_crawl
AKGENTIC_QDRANT_URL=http://localhost:6333
# AKGENTIC_QDRANT_API_KEY=  # only for a secured Qdrant
```

---

## 10. Build milestones

1. **Scaffold** — `uv init`, `pyproject.toml` with local `akgentic-tool` + `akgentic-llm` sources,
   `uv sync`, verify imports.
2. **Team core** — `tools.py`, `agents.py`, `team.py`; boot ActorSystem + 3 agents + HumanProxy in a
   throwaway script; confirm a query round-trips (in-memory backend first).
3. **Qdrant wiring** — run Qdrant locally, set `AKGENTIC_QDRANT_URL`, confirm ingest → persist → query.
4. **Backend API** — FastAPI `/ws/chat` + event bridge; manual test with a websocket client.
5. **Frontend** — minimal chat UI + "ingest URL" action against the backend.
6. **Dockerize** — backend + web Dockerfiles, `compose.yaml` with Qdrant; `make up` brings up the stack.
7. **Makefile + docs** — finalise targets, `.env.example`, `README.md`.
8. **Tests** — team-boot test + ingest/query integration test.

---

## 11. Decisions (all confirmed)

- **A — KnowledgeGraph.** Knowledge base is the `KnowledgeGraphTool` (entities + relations, hybrid
  search) backed by the shared `#VectorStore` (Qdrant).
- **B — Manager/router.** Lightweight `@Manager` routes to `@Knowledge` and `@WebIngest`.
- **C — Custom UI.** Custom FastAPI backend + static JS frontend (no Angular).
- **D — Latest releases** of `akgentic-core/agent/team`, verified by a post-`uv sync` smoke import.
- **E — Docker `build.context: ..`** so both local packages are in the image build context.
- **F — Model** = `gpt-5.6-luna` (OpenAI-compatible endpoint; `.env` provided by you).
- **G — Credentials** from your `.env` (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`).
- **H — No meta-package;** individual latest releases + local sources.
- **I — Community + AGPL** accepted; backend AGPL, custom frontend license-independent.
- **J — Local `akgentic-llm`** (`../akgentic-llm`, editable), same pattern as `akgentic-tool`.
- **K — Drop `akgentic-infra`;** the custom backend boots the actor system directly.

Plan is final — ready to implement on your go-ahead.
