# Persistent and selectable teams

> Implementation status: the YAML-backed single-active-team design described
> below is implemented. The backend resumes `data/active-team.json`, scopes URL
> state under the runtime UUID, and exposes the Teams screen for creating and
> activating instances. Advanced deletion and multi-process coordination remain
> future work.

## Conclusion

The current application can be changed to restart the same team and to select
from available teams. The two installed Akgentic packages provide complementary
parts of that solution:

- `akgentic-catalog` stores and resolves **team definitions**. A catalog
  namespace is a blueprint such as `knowledge-akgents-production`.
- `akgentic-team` creates, lists, stops, and resumes **team instances**. An
  instance has a runtime UUID, persisted events, agent snapshots, and lifecycle
  state.

Those identifiers are deliberately different. A catalog namespace does not
become the runtime team ID, and loading the same `TeamCard` twice creates two
independent team instances unless a team ID is explicitly supplied.

This distinction explains the current Qdrant behaviour. Knowledge points are
tagged with the runtime team UUID. `KnowledgeTeam` currently calls
`TeamFactory.build()` without a UUID, so every backend process gets a new one
and cannot see knowledge written by the previous process.

## What the frameworks already support

### Restarting a team

`akgentic-team` 1.8.0 provides the complete lifecycle needed by this sample:

- `TeamManager.create_team(...)` accepts a resolved `TeamCard`, an optional
  `team_id`, and an optional `catalog_namespace`;
- `YamlEventStore` persists the `Process`, event stream, agent snapshots, and
  content-addressed agent cards under a data directory;
- `EventStore.list_teams(...)` lists persisted instances and can filter by
  owner, lifecycle status, and indexed metadata;
- `TeamManager.stop_team(team_id)` performs a graceful stop and marks the
  process as stopped;
- `TeamManager.resume_team(team_id)` restores a stopped team with the same team
  UUID, reconstructed actors, replayed events, and restored agent state;
- `TeamManager.delete_team(team_id)` removes a stopped instance's team
  persistence.

Keeping the UUID is sufficient to regain access to that team's Qdrant points.
Using `TeamManager` adds restoration of actor state and conversation events
instead of preserving only the Qdrant scope.

The recommended solution is therefore full `TeamManager` persistence, not a
hard-coded UUID passed directly to `TeamFactory`. A fixed UUID would solve the
immediate knowledge-visibility symptom, but it would leave lifecycle,
conversation state, crash recovery, instance listing, and future team
selection as application-owned custom work.

### Listing definitions

`akgentic-catalog` can list team definitions without scanning YAML files in
application code:

```python
catalog.list(EntryQuery(kind="team"))
```

The catalog package also ships a `GET /catalog/namespaces` API that projects
team and namespace metadata for a picker. The sample does not need to mount the
complete catalog API initially; it can use the same public `Catalog.list(...)`
service and expose a narrow application DTO.

`Catalog.load_team(namespace)` remains the correct way to resolve the selected
definition into a native `TeamCard`.

### Listing instances

Available runtime instances come from:

```python
event_store.list_teams()
```

Each persisted `Process` includes:

- `team_id`;
- `status`;
- `team_name`;
- creation and update times;
- owner fields;
- `catalog_namespace`.

The last field is important: `TeamManager.create_team()` can record which
catalog namespace produced an instance, but `akgentic-team` intentionally
treats it as an opaque tag. The application is responsible for joining
catalog definitions and runtime instances in its API and UI.

## Important semantics

### Resume does not reload the catalog

A resumed instance is rebuilt from its persisted structural projection and
stored agent cards. This is desirable for reproducibility: stopping and
starting a team does not silently change its prompts, tools, model
configuration, or topology because a catalog file changed.

It also means there must be two explicit user operations:

1. **Resume instance** continues the existing team, identity, state, and
   knowledge scope.
2. **Create instance from definition** resolves the current catalog namespace
   and creates a new team instance.

Applying a changed catalog definition to an existing runtime UUID is a separate
migration problem. It should not be part of the first implementation because
the framework has no simple “rebase this persisted process onto this new
TeamCard” lifecycle operation.

### Graceful restart and crash recovery differ

The normal shutdown path should call `TeamManager.stop_team()`. On the next
application start, that process is `STOPPED` and can be resumed normally.

After an ungraceful process or container crash, the YAML record may still say
`RUNNING` although no actors exist. `resume_team()` correctly refuses that
state. In this single-backend sample, startup can reconcile it by calling
`stop_team()` on the stale process; the manager detects that no local runtime
is tracked, changes only the persisted state to `STOPPED`, and then the
application can resume it.

That recovery rule is only safe while one backend process owns the event-store
directory. A multi-worker or horizontally scaled deployment would require a
real service registry, leases, or heartbeats before deciding that a persisted
`RUNNING` instance is stale.

### Team knowledge includes more than Qdrant

The following state must use the same team boundary:

| State | Required scope |
|---|---|
| Qdrant points | Existing `team_id` payload filter |
| Events and agent snapshots | `YamlEventStore/<team-id>/` |
| Imported URL records and source ownership | One repository per `team_id` |
| Active selection | Persisted runtime `team_id` |
| Catalog origin | `Process.catalog_namespace` |

The current global `data/urls.json` is therefore incorrect once more than one
team instance is selectable. It could report a URL as ingested even when the
active team's Qdrant scope contains none of its knowledge. The repository
should move to a team-scoped path such as:

```text
data/
├── active-team.json
├── teams/
│   ├── agent_cards/
│   └── <team-id>/
│       ├── team.yaml
│       ├── events.yaml
│       ├── states/
│       └── urls.json
```

`YamlEventStore` owns all paths shown except `active-team.json` and
`urls.json`. The application owns those two files.

## Recommended product model

For the first version, support **one active runtime instance at a time**, while
allowing multiple stopped instances to be stored and selected.

This is preferable to running all teams concurrently because the current web
application has:

- one global `KnowledgeTeam`;
- one shared WebSocket broadcast channel;
- one global URL repository;
- no team identifier on browser chat sessions.

Running multiple teams simultaneously without first changing those boundaries
would mix event streams and make it unclear which team receives a message.
Stopping the active team and resuming the selected team gives the sample real
team selection while keeping chat and evaluation semantics unambiguous.

Initially allow multiple instances from the same catalog definition. A single
instance per namespace sounds simpler, but prevents useful isolated knowledge
bases such as “production documentation” and “customer A documentation” that
share one team blueprint. The UI can show the catalog namespace and creation
time so those instances remain distinguishable.

## Implementation plan

### Phase 1: Introduce a persistent runtime service

Replace the direct `TeamFactory` ownership in `KnowledgeTeam` with an
application service that owns:

- one `ActorSystem`;
- one `YamlEventStore`, configured under the persisted application data
  directory;
- one `TeamManager`;
- the currently active `Process` and `TeamRuntime`;
- the existing `WebEventBridge` and any tracing/evaluation subscribers.

Keep a small send/roster surface so `app.py` does not become coupled to
`TeamManager` internals.

On creation:

1. Resolve the selected namespace with `Catalog.load_team(namespace)`.
2. Apply runtime bindings such as model configuration.
3. Create the team-specific URL repository path before binding the web tool.
4. Set `TeamCard.message_types` as the current wrapper does.
5. Call `TeamManager.create_team(..., catalog_namespace=namespace)`.
6. Persist the returned team ID as the active selection.

On shutdown, call `TeamManager.stop_team(active_team_id)` before shutting down
the actor system.

### Phase 2: Persist and restore the active selection

Add a small atomic JSON registry containing the selected runtime UUID. It
should be separate from event-store internals rather than inferred from
directory ordering.

Startup resolution should follow this order:

1. Use an explicitly configured team ID when provided for operational recovery.
2. Otherwise read `active-team.json`.
3. Otherwise find the newest persisted instance whose
   `catalog_namespace` is the configured default production namespace.
4. Otherwise create a new instance from the default production namespace.

For the selected process:

- `STOPPED`: resume it;
- stale `RUNNING` in this single-process deployment: reconcile to `STOPPED`,
  then resume;
- missing or corrupt: report a startup error instead of silently creating a
  new identity and hiding the old knowledge;
- `DELETED`: reject the selection and require another instance.

The first upgrade from the current application cannot discover the old
ephemeral team UUID after the process that owned it has stopped, because that
UUID was never persisted by the application. Treat the upgrade as the creation
of the first managed instance. Existing orphaned Qdrant points can only be
removed through the existing storage reset unless their team UUID is recovered
from point payloads deliberately.

### Phase 3: Scope imported URLs to the runtime team

Change URL repository construction from one settings-level singleton path to a
factory:

```python
url_repository_for(team_id)
```

The `ChangeAwareWebTool` bound into a newly created team receives that team's
path. A resumed team restores the repository path stored in its persisted agent
card configuration, so paths must be stable inside the container and backed by
the same Docker volume.

Before relying on that behaviour, add a focused round-trip test that creates,
stops, and resumes the production `TeamCard` and confirms the configured
repository path survives card serialization. If it does not, the application
must apply a documented runtime-path rebinding during restoration rather than
silently falling back to a global path.

### Phase 4: Add narrow backend APIs

Expose application-focused endpoints rather than the full generic catalog
administration API:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/team-definitions` | List catalog namespaces containing a team |
| `GET` | `/api/team-instances` | List persisted processes and active state |
| `GET` | `/api/team-instances/active` | Return active definition, UUID, status, and counts |
| `POST` | `/api/team-instances` | Create and activate an instance from a namespace |
| `POST` | `/api/team-instances/{id}/activate` | Stop current instance and resume the selected one |
| `POST` | `/api/team-instances/{id}/stop` | Stop a non-active or active running instance |
| `DELETE` | `/api/team-instances/{id}` | Delete a stopped instance with explicit knowledge policy |

Activation must be serialized with a lock:

1. reject new sends during the transition;
2. gracefully stop the active runtime;
3. resume the target;
4. switch the team-scoped URL repository;
5. atomically persist the active ID;
6. publish a team-changed event;
7. accept chat messages again.

If target startup fails, attempt to resume the previous instance and keep the
active registry unchanged. Return an error if rollback also fails.

Lifecycle endpoints should not be exposed as anonymous production
administration by default. For this sample, gate them behind an explicit
configuration switch and document that authentication is required before
internet exposure.

### Phase 5: Extend Settings with team selection

Add two clearly labelled sections:

- **Team definitions** shows catalog namespace, display name, description, and
  whether it can create an instance.
- **Team instances** shows UUID, originating namespace, lifecycle state,
  created/updated timestamps, active state, tracked URL count, and scoped
  Qdrant point count.

Use “Create instance” for definitions and “Activate” or “Resume” for instances.
Do not label both lists simply “teams”; that would hide the central distinction
between reusable configuration and persisted state.

The main header should show the active team display name and a shortened UUID.
Switching should require explicit confirmation when the current team is
processing work.

The evaluation namespace should be hidden from the ordinary production picker
by default. Add catalog metadata such as
`properties.purpose: evaluation`, and filter it unless a development setting
enables evaluation definitions.

### Phase 6: Make status and cleanup team-aware

Extend `/api/system/status` with:

- active runtime team ID;
- active catalog namespace;
- lifecycle status;
- team-scoped Qdrant point count;
- team-scoped URL count;
- whether those two stores are consistent.

Define deletion semantics explicitly:

- deleting `YamlEventStore` data alone leaves orphaned Qdrant points;
- deleting Qdrant points alone leaves URL ownership and runtime history that
  claim the knowledge still exists.

The application-level delete operation should therefore offer one safe default:
delete the stopped runtime instance, its URL repository, and its Qdrant points
as one coordinated operation. If retention of knowledge is ever needed, expose
it as an explicit advanced policy rather than the default.

The existing full reset should continue deleting all application state and the
Qdrant collection together. It must also include the new team event-store and
active-selection files through their shared Docker volume.

### Phase 7: Make evaluations record team identity

The running-system evaluation adapter should query active-team status before a
run and add at least these values to report metadata:

- runtime team UUID;
- catalog namespace;
- team definition display name;
- process creation/update timestamps.

Each WebSocket evidence event should carry `team_id`. That makes evidence safe
to filter now and prepares for concurrent teams later.

For repeatable end-to-end evaluation, optionally accept an expected team ID or
catalog namespace and fail before paid model calls if the running application
has selected a different team.

The RAG4j dataset is the acceptance scenario: ingest with one managed team,
restart the backend, confirm the UUID is unchanged, and run the live dataset
against the restored team without re-ingesting the page.

### Phase 8: Test the lifecycle boundaries

Add focused tests for:

1. First startup creates and records one production instance.
2. Graceful shutdown persists `STOPPED`.
3. Restart resumes the same UUID.
4. Knowledge written before restart remains visible after restart.
5. Agent state and event sequence continue after resume.
6. A stale `RUNNING` process is recovered only in configured single-instance
   mode.
7. Catalog definitions and runtime instances are listed separately.
8. Two instances created from one namespace remain isolated in Qdrant and URL
   state.
9. Switching teams stops the old runtime before activating the new runtime.
10. A failed activation rolls back to the previous team.
11. A catalog edit does not mutate a resumed instance.
12. Creating a new instance uses the edited catalog definition.
13. Deletion removes team persistence, URL state, and scoped Qdrant data.
14. Live evaluation metadata identifies the exact active instance.

Use the real `YamlEventStore` in temporary directories for lifecycle tests.
Mock model and web dependencies where possible; reserve the existing paid live
evaluation for final acceptance.

## Recommended delivery sequence

Implement the work in four reviewable increments:

1. **Persistence:** `TeamManager`, `YamlEventStore`, graceful stop, startup
   resume, stable UUID, and migration behaviour.
2. **State isolation:** team-scoped URL repositories and team-aware system
   status.
3. **Selection:** definition/instance APIs, Settings UI, activation rollback,
   and safe deletion.
4. **Evaluation:** report identity metadata, evidence filtering, and the
   restart-without-reingestion acceptance run.

Do not begin with the selector UI. Stable lifecycle and state isolation must be
proven first; otherwise the UI would make it easy to create apparently valid
teams whose URL records and Qdrant knowledge do not match.

## Decision summary

- Use `TeamManager` and `YamlEventStore` for this Docker sample.
- Persist generated runtime UUIDs; do not derive them from catalog namespace.
- Treat catalog namespaces as definitions and `Process` records as instances.
- Permit multiple stored instances per definition, with only one active at a
  time.
- Resume the persisted instance to preserve knowledge visibility and actor
  state.
- Keep URL ownership, Qdrant knowledge, events, and active selection scoped to
  the same runtime UUID.
- Treat catalog updates as new-instance creation until a deliberate migration
  design exists.
- Use MongoDB or PostgreSQL only when the application becomes multi-instance;
  YAML is the framework's shipped default and fits the current single-container
  backend.
