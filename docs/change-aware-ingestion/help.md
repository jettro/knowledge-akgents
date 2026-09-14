# Change-aware ingestion

Knowledge Akgents uses a normalized SHA-256 hash to avoid repeating LLM
extraction and graph updates when Tavily returns the same content for a URL.
Tavily does not expose origin-page ETags, Last-Modified values, or conditional
request support, so the Tavily extraction request still occurs.

## Stored state

`data/teams/<runtime-team-id>/urls.json` keeps submission history separately
from ingestion state. Each persisted team therefore has URL ownership records
that match its Qdrant `team_id` scope:

- when the URL was last submitted and checked;
- the hash and timestamp of the last successful ingestion;
- separate submission, check, and ingestion counters;
- the latest status: `ingested`, `unchanged`, or `failed`;
- entity names and relation triples attributed to the last successful version;
- optional ETag and Last-Modified fields reserved for future retrieval support.

Missing fields in an existing team-scoped `urls.json` receive safe defaults
when the file is loaded.

## Ingestion sequence

For new or changed extracted content:

1. `web_fetch_tool` calls Tavily and hashes normalized `raw_content`.
2. It returns the content with `content_hash` and `content_status`.
3. `@WebIngest` extracts knowledge and calls `update_graph`.
4. Only after that succeeds, it calls `commit_web_ingestion`.

The commit tool accepts only a hash returned by the current web-tool instance.
If the graph update fails, `fail_web_ingestion` discards the pending candidate
and preserves the previous successful hash.

The commit also records the complete ownership manifest supplied by
`@WebIngest`: all entity names and relation triples represented by that source
after the update.

For unchanged content, the wrapper places the URL and hash in
`unchanged_results` and omits `raw_content`. The agent must not call
`update_graph`.

## Force behavior

Force is opt-in. The user must explicitly request forced reprocessing, after
which the agent calls `web_fetch_tool` with `force=true`. Identical content is
then returned normally and must follow the same update-then-commit sequence.

## Important limitation

The hash represents Tavily's query-filtered extracted text, not the complete
origin response. It is therefore a practical duplicate-processing guard, not a
strong HTTP change validator:

- Tavily is still called and still incurs its normal latency and cost;
- a different extraction query can return different chunks for an unchanged
  page;
- Tavily extraction changes can also produce a different hash;
- equal extracted content reliably skips ingestion, but unequal extracted
  content does not prove that the origin page changed.

Do not describe this mechanism as ETag-equivalent. Native HTTP validators would
still be preferred if Tavily or Akgentic exposes them later.

## Replacing changed source facts

When a hash changes, `web_fetch_tool` returns `previous_source_facts`. This
contains only facts from the source's previous committed manifest that are not
also claimed by another tracked URL.

`@WebIngest` performs replacement in one `update_graph` request:

1. update entities that remain present;
2. create new entities and relations;
3. delete previous relations no longer supported;
4. delete previous entities no longer supported;
5. commit the new complete ownership manifest.

The graph tool executes entity and relation deletion by their stable names and
triples. Shared facts are excluded from the deletion candidates because the
current graph model has one global entity description rather than separate
per-source assertions.

This protects facts explicitly owned by another URL, but it cannot provide
fully independent per-source descriptions for a shared entity. That would
require a future provenance-aware graph model.

## Evaluation

The no-network tests cover repository transitions and wrapper behavior:

```bash
make test-evals
```

The live fixed-fixture scenario is:

```bash
make eval-change-aware-ingestion
```

It makes paid model calls but does not use Tavily. One case checks that a second
identical ingestion skips `update_graph`, one checks that an explicit force
request performs a second update, and one changes the fixture and requires
stale source-owned facts to be deleted. All verify the required
fetch-to-update-to-commit ordering.
