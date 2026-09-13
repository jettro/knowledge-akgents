# Qdrant Evaluation Follow-up

## Purpose

This document records the deferred work for running Knowledge Akgents
evaluations against real Qdrant storage. It exists so the topic can be resumed
after the ongoing Qdrant refactoring in Akgentic has stabilized, without
repeating the investigation.

Decision date: 2026-09-13.

## Current decision

Do not change `KnowledgeGraphTool` or add application-level collection-name
workarounds yet.

Continue using:

- fixture-backed deterministic evaluations for fast local and CI checks;
- in-memory knowledge storage for routine paid model evaluations;
- the existing dependency-injection seams in `KnowledgeTeam` for evaluation
  tools;
- explicit approval before paid or externally connected evaluation runs.

Do not run evaluations against production Qdrant. The existing
`--allow-persistent-store` option may only be used with an ephemeral or
dedicated evaluation Qdrant instance.

The reason for deferral is that Akgentic's Qdrant integration is undergoing a
larger refactoring. Building a collection-name abstraction in Knowledge Akgents
now could duplicate or conflict with the resulting framework API.

## What the investigation found

The current Akgentic Tool source is in `../akgentic-tool/`.

### Knowledge graph collection

`../akgentic-tool/src/akgentic/tool/knowledge_graph/kg_actor.py` currently
defines:

```python
KG_COLLECTION: str = "knowledge_graph"
```

`KnowledgeGraphActor` uses that constant for collection creation, embedding
writes, searches, and removals.

`KnowledgeGraphTool` exposes a `collection: CollectionConfig` field, but this
configures collection behavior rather than its name. The current fields include:

- backend;
- embedding dimension;
- optional tenant;
- backend-specific parameters.

Therefore, the physical collection name is not currently configurable through
the public `KnowledgeGraphTool` API.

### Existing Qdrant isolation

The current Qdrant backend already provides stronger isolation than the shared
collection name initially suggested.

`../akgentic-tool/src/akgentic/tool/vector_store/qdrant.py`:

- stores the owning actor team's `team_id` on every point;
- includes the `team_id` in every search and removal filter;
- optionally includes `CollectionConfig.tenant` in points and filters;
- derives point IDs from `team_id`, tenant, and reference ID;
- exposes `delete_by_team(collection, team_id)` for scoped cleanup.

As a result, two actor teams using the physical `knowledge_graph` collection
should not see each other's vector entries. Since the evaluation task adapter
creates a fresh `KnowledgeTeam` per case, Qdrant team scoping should provide
case isolation.

This behavior still needs an integration test against the refactored Qdrant
implementation before relying on it.

### Why collection naming may still be useful

Configurable collection names are not a prerequisite for isolated evaluations,
but they may remain useful for:

- visually distinguishing production and evaluation data;
- deleting an entire evaluation collection;
- using different embedding dimensions or collection schemas;
- applying different Qdrant indexing parameters;
- reducing the blast radius of cleanup or administrative mistakes;
- inspecting evaluation data directly in Qdrant tooling.

Whether this is still necessary should be reassessed after the framework
refactoring.

## Current Knowledge Akgents behavior

Routine evaluation Make targets force:

```bash
AKGENTIC_QDRANT_URL=''
```

This selects in-memory storage and prevents accidental writes to a configured
persistent Qdrant instance.

The live evaluation runner refuses persistent Qdrant unless
`--allow-persistent-store` is explicitly provided.

The relevant files are:

- `evals/harness/tasks.py` — creates a fresh `KnowledgeTeam` for every case;
- `evals/runners/evaluate.py` — persistent-store safety check;
- `src/knowledge_akgents/team.py` — team and tool wiring;
- `src/knowledge_akgents/tools.py` — production vector and graph tool cards;
- `evals/datasets/jettro_scenario.py` — fixed-fixture end-to-end scenario;
- `evals/datasets/yuma_scenario.py` — fixed-fixture end-to-end scenario.

The retrieval-only dataset injects a fixture-backed `search_graph` tool and
therefore does not exercise Qdrant. The Jettro and Yuma ingestion scenarios are
the appropriate starting points for Qdrant integration evaluation.

## Recommended future test topology

Keep three separate evaluation layers.

### 1. Deterministic fixture tests

Continue running these by default:

```bash
make test-evals
```

They validate routing, tool arguments, event correlation, answer contracts,
judge calibration, and harness behavior without Qdrant or external web traffic.

### 2. Qdrant integration evaluations

Run fixed web fixtures and the configured model against a real Qdrant backend.
These evaluations should test:

- Qdrant collection creation;
- embedding writes;
- hybrid, vector, and keyword retrieval;
- team and tenant isolation;
- cleanup;
- Jettro and Yuma ingestion-to-retrieval behavior.

Use an ephemeral Qdrant container where possible. A dedicated shared evaluation
Qdrant is the second choice. A production Qdrant cluster must not be used.

### 3. Fully live evaluations

Real web retrieval plus real Qdrant should remain a separate, less frequent
experiment because it combines model, provider, network, page-content, and
storage variance.

## Work to perform after the framework refactor

1. Review the final Akgentic Qdrant and vector-store APIs.
   - Check whether collection naming has become configurable.
   - Check whether team and tenant filtering behavior changed.
   - Check whether cleanup is available through a public tool or lifecycle API.
   - Check whether graph state and vector state have matching persistence
     semantics.

2. Update the local Akgentic dependencies and run their relevant tests.
   - Knowledge graph actor tests.
   - Qdrant backend tests.
   - Team-isolation and cleanup tests.

3. Choose the Qdrant evaluation topology.
   - Preferred: disposable Qdrant container per evaluation session.
   - Alternative: dedicated long-running evaluation Qdrant.
   - Reject: production Qdrant, even with a separate tenant or collection.

4. Decide the isolation mechanism based on the final API.
   - Unique physical collection per run, if supported and useful.
   - Unique tenant per run.
   - Framework-generated team ID.
   - A documented combination of the above.

5. Expose only the required application configuration.
   Possible settings, subject to the final framework API:

   ```text
   AKGENTIC_QDRANT_URL
   AKGENTIC_KNOWLEDGE_COLLECTION
   AKGENTIC_KNOWLEDGE_TENANT
   ```

   Do not add settings that merely duplicate framework defaults.

6. Ensure query and ingestion use identical storage configuration.
   `@Knowledge` and `@WebIngest` must resolve the same collection, tenant, vector
   store, embedding model, and embedding dimension.

7. Add an explicit Qdrant evaluation runner or Make target.
   It should fail unless the configured URL is clearly intended for evaluation.
   Prefer a separate setting such as `AKGENTIC_EVAL_QDRANT_URL` over weakening
   the existing persistent-store guard.

8. Add lifecycle cleanup.
   Cleanup must run in `finally`, including after task, model, evaluator, or
   timeout failures. Depending on the final API, cleanup may delete:

   - the complete temporary collection;
   - the temporary tenant;
   - all points belonging to the evaluation team ID;
   - the disposable Qdrant container.

9. Add storage-isolation tests before running paid scenarios.
   - Team A writes a unique fact.
   - Team B cannot retrieve Team A's fact.
   - Team B writes another unique fact.
   - Team A cannot retrieve Team B's fact.
   - Cleanup removes only the intended evaluation data.
   - Production-like data outside the evaluation scope remains unchanged.

10. Run the fixed Jettro scenario against Qdrant.
    Compare it with the established in-memory baseline:

    - assertions;
    - route;
    - graph tool calls;
    - retrieved facts;
    - duration;
    - request and token usage;
    - search count and search modes.

11. Run the fixed Yuma scenario against Qdrant.
    Pay particular attention to retrieval of all six companies and the
    normalization of Aprico Consulting versus Aprico Consultants.

12. Save native Pydantic Evals reports for comparison.

    ```bash
    --save-report eval-reports/qdrant-baseline.json
    --baseline eval-reports/qdrant-baseline.json
    ```

13. Use the existing production/evaluation catalog split when storage
    configurations stabilize. `knowledge-akgents-production` provides the
    exact production team definition, while `knowledge-akgents-evaluation`
    supports deterministic fixture replacement outside application code.
    Storage mode remains a runtime concern: use a dedicated Qdrant URL and
    explicit cleanup rather than encoding one mutable test database into the
    team definition.

## Current catalog composition

Knowledge Akgents now uses `akgentic-catalog` directly. A
`YamlEntryRepository` reads two version-controlled namespaces:

- `knowledge-akgents-production` owns the reviewed team, agents, prompts,
  model, and tools;
- `knowledge-akgents-evaluation` owns a separate team entry that references
  the shareable production agents.

Catalog entries own prompts, agent metadata, the shared model definition, tool
cards, and the Human entry point. Python owns settings-based model and path
bindings, fixture implementations, subscribers, and the runtime wrapper.
`TeamFactory` performs actor construction and role-catalog registration after
the catalog resolves the team.

`KnowledgeTeam` now accepts a resolved `TeamCard` and has no evaluation
profile or fixture-tool parameters. `evals/harness/catalog.py` loads the evaluation
team and replaces the resolved `web` and read-only knowledge cards when a case
provides fixtures. Fixture state remains case-specific runtime data rather than
durable catalog configuration.

The production namespace is also available as a live end-to-end evaluation
tier. The current runner combines it with temporary URL state and in-memory
Qdrant by default, so selecting production configuration does not select
production data. It uses real Tavily and model calls. A future real-Qdrant tier
should add:

- a dedicated collection or ephemeral Qdrant instance;
- an ownership label for cleanup;
- refusal of known production endpoints unless separately authorized.

Add them only when the catalog can express the final storage
configuration and lifecycle:

- custom or fixture-backed tool cards;
- shared vector-store and knowledge-graph configuration between agents;
- collection and tenant settings from the refactored framework;
- production-safe defaults;
- evaluation-specific configuration without modifying production YAML;
- event subscribers required by the evaluation collector;
- deterministic lifecycle and cleanup for Qdrant-backed runs.

Catalog replaces configuration and assembly without reducing testability.
Registered Python tool-card overrides remain the explicit mechanism for fixture
tools and other controlled implementations that do not belong in YAML.

## Acceptance criteria

The Qdrant integration layer is ready when:

- no test can connect to production Qdrant accidentally;
- each evaluation run has a documented and verified isolation boundary;
- ingestion and query actors share the intended storage configuration;
- Jettro and Yuma pass their deterministic contracts using real Qdrant;
- cross-team data leakage tests pass;
- cleanup is verified after both successful and failed cases;
- repeated runs do not accumulate unbounded evaluation data;
- Qdrant-specific failures are distinguishable from model and evaluator
  failures;
- routine `make test-evals` remains fast and independent of Qdrant;
- paid Qdrant evaluations remain explicit, manual, or scheduled.

## Open questions for the later review

- Does the refactored framework expose a collection name on
  `KnowledgeGraphTool`?
- Is `team_id` stable for restored production teams and unique for evaluation
  teams?
- Is tenant isolation supported consistently across Qdrant, Weaviate, and
  in-memory backends?
- Is `delete_by_team` exposed through a public lifecycle API?
- Does cleanup need to remove graph actor state as well as vector entries?
- Can an ephemeral Qdrant URL be configured without affecting application
  settings loaded from `.env`?
- Should Qdrant integration run locally only, in scheduled CI, or both?
- Should ephemeral-Qdrant and fully live behavior use separate catalog
  namespaces or settings applied after loading the existing namespace?
- Can collection, tenant, and cleanup configuration remain serializable
  catalog data, or do lifecycle handles require a runtime binding?
