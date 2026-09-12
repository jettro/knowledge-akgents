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
separate from the knowledge graph itself. This is *only* an input history (url, first/last
imported timestamps, how many times it was submitted); it doesn't affect ingestion or
retrieval. The frontend shows it in the **Imported URLs** panel (fetched from
`GET /api/urls`), so you can see at a glance what has already been fed into the system.

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

## Project layout

```
src/knowledge_akgents/   settings, tools, agents, events bridge, team wiring, FastAPI app
                         (repository.py tracks imported URLs in data/urls.json)
frontend/                static Human-Proxy UI + nginx config
docker/                  backend & web Dockerfiles
compose.yaml             qdrant + backend + web
data/                    local cache (imported-URL history); gitignored, safe to delete
```

## License

AGPL-3.0-only (the akgentic packages this depends on are AGPL-3.0).
