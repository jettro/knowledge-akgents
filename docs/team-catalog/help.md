# Team catalog

Knowledge Akgents stores two teams under `config/catalog/`:

- `knowledge-akgents-production` is the reviewed application team;
- `knowledge-akgents-evaluation` is the fixture-capable evaluation team.

Both are loaded with `Catalog(YamlEntryRepository(...)).load_team(...)`, which
returns the native Akgentic `TeamCard` consumed by `KnowledgeTeam` and
`TeamFactory`. The application does not maintain a parallel catalog schema.

## Namespace topology

The production namespace contains:

- one `team` entry describing the entry point and member tree;
- four `agent` entries;
- three `prompt` entries using `NativeValue`;
- one shared `model` entry;
- four `tool` entries.

Its `_meta` entry marks the namespace as `shareable: true`. The evaluation
namespace contains its own `_meta` and `team` entries. That team uses
cross-namespace references to the reviewed production agents, which in turn
reference the production prompts, model, and tools.

This creates two independently selectable teams without copying prompts or
agent definitions. Production prompt and topology changes are therefore
exercised by both teams. If an evaluation later needs a deliberately different
agent or prompt, it can add an evaluation-owned entry and point only that team
member at it.

## Runtime bindings

The resolved catalog remains configuration, not live application state.
`src/knowledge_akgents/catalog.py` applies two narrow runtime bindings after
`Catalog.load_team()`:

- the configured provider and model from application settings replace the
  catalog's reviewed defaults;
- the change-aware web tool receives the selected URL repository path.

`KnowledgeTeam` accepts an already resolved `TeamCard`; it does not know about
catalog namespaces, runtime profiles, or evaluation fixtures. Production
startup loads `knowledge-akgents-production` before constructing the runtime.

`evals/catalog.py` owns evaluation composition. It loads
`knowledge-akgents-evaluation` and replaces only the case-specific web or
read-only knowledge tool when a deterministic fixture is requested. No
evaluation-specific tool arguments flow through `src/`.

## Production end-to-end evaluations

The evaluation runner can instead load `knowledge-akgents-production`
unchanged with `--catalog-team production`. This verifies the exact production
team definition, including prompts, topology, agent classes, and tool cards.

Catalog selection and infrastructure selection are separate:

- the URL repository is always placed in the case's temporary directory;
- Make targets clear `AKGENTIC_QDRANT_URL`, selecting the isolated in-memory
  store;
- the production web tool makes real Tavily calls;
- model calls are paid;
- Logfire export remains opt-in;
- a configured persistent Qdrant is rejected unless
  `--allow-persistent-store` is explicit.

Only ingestion and ingestion-plus-retrieval scenarios support the production
team. Retrieval-only and synthetic-failure scenarios require fixture tools and
therefore remain evaluation-team scenarios.

## Application model allowlist

The web tool entry uses the application model type
`knowledge_akgents.change_aware_web.ChangeAwareWebTool`. Startup adds only the
narrow `knowledge_akgents.change_aware_web.` prefix to the catalog model-type
allowlist. Other application modules are not authorized as catalog
`model_type` values.

The actor classes are dotted paths inside `AgentCard.agent_class`; they remain
the trace-context-aware subclasses used by the local actor runtime.

## Validation

`load_team_card()` calls `Catalog.validate_namespace()` before resolving either
team. This matters for a version-controlled YAML repository: direct file edits
must receive the same unknown-key, cross-namespace reference, ownership, and
namespace checks as catalog writes and bundle imports.

After changing catalog entries, run:

```bash
make test
make test-evals
```

Prompt changes affect paid model behavior and should be followed by the
relevant targeted live evaluation after explicit approval.
