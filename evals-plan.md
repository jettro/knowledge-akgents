# Evaluation plan for Knowledge Akgents

## Purpose and scope

This document proposes how to introduce evaluations for Knowledge Akgents using
Pydantic Evals. It is a design and rollout plan only; it does not implement an
evaluation harness or change the running application.

The plan is based on:

- the current application architecture in this repository;
- Pydantic Evals and Logfire documentation available on 2026-09-12;
- the installed dependency graph, which currently includes Pydantic AI 2.43.0,
  Pydantic Evals 2.43.0, and Logfire 5.1.0 transitively;
- the current Akgentic LLM implementation, which wraps `pydantic_ai.Agent`;
- the current Akgentic event stream, which emits `ToolCallEvent` and
  `ToolReturnEvent`.

## Executive recommendation

Pydantic Evals is a good candidate for this project and is worth adopting through
a focused pilot.

The strongest reasons are:

1. It is independent of Pydantic AI at the dataset and evaluator level. The task
   being evaluated can be any Python callable, so the actor-based `KnowledgeTeam`
   can be wrapped in an evaluation adapter.
2. It supports deterministic evaluators, custom evaluators, LLM judges, case
   metadata, lifecycle hooks, experiment metadata, concurrency controls, and
   serializable datasets.
3. It captures OpenTelemetry spans during task execution. Akgentic's LLM layer
   internally uses Pydantic AI, so model and tool execution spans should be
   available after Pydantic AI instrumentation is enabled before agents are
   constructed.
4. It integrates directly with Logfire for experiment comparison without making
   Logfire the source of truth or the component that executes evaluations.

There is one important qualification: using Pydantic models in Akgentic is not
what makes the integration work. The useful compatibility comes from Akgentic's
LLM layer wrapping `pydantic_ai.Agent`, plus Akgentic's own event stream. Pydantic
AI instrumentation can observe the inner model and tool execution, while a small
evaluation adapter will still be needed to represent the outer actor routing,
messages, completion, and final result in a stable form.

The recommended starting position is:

- keep evaluation code and datasets in this repository;
- keep them outside the production package and ordinary unit-test suite;
- make Pydantic Evals and Logfire explicit evaluation dependencies rather than
  relying on their current transitive installation;
- build one reusable task adapter around `KnowledgeTeam`;
- collect both OpenTelemetry spans and Akgentic events;
- start with a small, curated, code-reviewed dataset;
- run deterministic and mocked evaluations frequently;
- run live-model and LLM-judge evaluations manually or on a schedule until their
  variance, cost, and thresholds are understood.

## Answers to the main design questions

### Should evaluations live in this project or in a separate project?

They should initially live in this repository, but as a clearly separated
subsystem.

Recommended structure:

```text
knowledge-akgents/
├── src/knowledge_akgents/       # production application
├── tests/                       # conventional deterministic unit/integration tests
├── evals/
│   ├── datasets/                # version-controlled YAML or JSON cases
│   ├── evaluators/              # custom deterministic and span/event evaluators
│   ├── tasks/                   # adapters that run the application for one case
│   ├── fixtures/                # controlled knowledge and tool responses
│   ├── run.py                   # evaluation entry point
│   └── README.md                # commands, required credentials, and data policy
└── pyproject.toml
```

This is preferable to a separate repository now because the evaluations are
tightly coupled to:

- agent prompts and role definitions in `agents.py`;
- tool composition in `tools.py`;
- actor and routing behavior in `team.py`;
- event shapes in `events.py`;
- dependency versions in `uv.lock`;
- application changes that should update or add regression cases.

Keeping these together makes a prompt, tool schema, model, or orchestration change
reviewable alongside the evaluation cases it affects. It also makes it easy to run
the candidate code from a branch without publishing or installing it elsewhere.

The separation should be operational rather than repository-level:

- use a dedicated dependency group such as `eval`;
- use separate commands from `pytest`;
- use separate environment variables and Logfire service/environment names;
- store datasets and evaluators under `evals/`, not under the production package;
- do not execute live evaluations as part of normal application startup.

A separate repository becomes reasonable later if one or more of these conditions
appear:

- the same benchmark must compare multiple independently versioned applications;
- evaluation datasets are owned by a different team or have stricter access rules;
- cases contain sensitive production examples that cannot be distributed with the
  application source;
- a central evaluation service needs to test released artifacts rather than a
  working tree;
- application and evaluation release cycles become intentionally independent.

Until then, a second repository would add version-skew, duplicated setup, and more
difficult branch comparisons without solving a current problem.

### How should tool behavior be evaluated?

Tool evaluation should be split into three layers. An end-to-end agent evaluation
is not a replacement for direct tool tests, and direct tool tests cannot prove
that the agent selected and called the tool correctly.

#### Layer 1: direct tool tests

Test tool implementation behavior without an LLM:

- valid inputs return the expected structured result;
- invalid inputs produce the intended validation or error;
- timeouts and upstream errors are surfaced correctly;
- knowledge writes can be read back from the same store;
- search and ingestion configuration is correct;
- external clients can be replaced with fakes or local fixtures.

These belong in `tests/` because they are ordinary deterministic software tests.
They should remain fast, cheap, and suitable for every pull request.

The current repository mostly tests tool presence on agent cards, not tool
behavior. Direct tool tests should therefore be added before depending on
end-to-end evaluations to diagnose tool failures.

#### Layer 2: tool contract tests

Test the interface exposed to the model:

- the intended tools are attached to each agent;
- read-only and write-enabled knowledge tools remain distinct;
- argument schemas contain the expected required fields and types;
- tool names and descriptions are sufficiently clear;
- representative argument payloads validate;
- dangerous or irrelevant parameters are not exposed.

These are also deterministic tests. They protect against a tool schema changing
silently and causing the model to produce different calls even though the Python
implementation still works.

#### Layer 3: agent tool-use evaluations

Run the agent and evaluate its decisions:

- whether a tool was called when required;
- whether a tool was avoided when not required;
- which tool was selected;
- the number and order of calls;
- whether call arguments preserve the user's URL, query, focus, or constraints;
- whether arguments are semantically appropriate rather than merely valid JSON;
- whether the tool returned successfully;
- whether the agent used the returned information in its final response;
- whether the manager delegated to the correct specialist.

For Knowledge Akgents, this layer should use two evidence sources.

**OpenTelemetry spans** should be the primary evidence for Pydantic AI model calls,
tool execution, duration, token use, cost, and exceptions. Pydantic Evals exposes
the case's span tree to evaluators and provides `HasMatchingSpan` for simple
queries.

**Akgentic events** should be captured for actor-level behavior. The framework
already emits:

- `ToolCallEvent` with `run_id`, `tool_name`, `tool_call_id`, and raw JSON
  `arguments`;
- `ToolReturnEvent` with matching identifiers and a success flag;
- sent-message events that identify sender and recipient.

The existing `WebEventBridge` is useful proof that this information is available,
but it should not be the evaluation interface. It currently converts tool
arguments to a display string and does not publish `ToolReturnEvent`. An
evaluation-specific subscriber should retain the raw identifiers and arguments,
parse JSON explicitly, correlate calls with returns, and collect message routing.
That produces stable structured evidence for custom evaluators.

Examples of custom deterministic evaluators needed for this project:

- `DelegatedTo(expected_agent="@Knowledge")`;
- `DelegatedTo(expected_agent="@WebIngest")`;
- `CalledTool(expected_tool="...")`;
- `DidNotCallTool(forbidden_tool="...")`;
- `ToolCallCount(minimum=1, maximum=3)`;
- `ToolArgumentsMatch(tool=..., expected_subset={...})`;
- `ToolArgumentSemanticMatch(...)` for cases where exact text is too strict;
- `AllToolCallsReturnedSuccessfully`;
- `ToolCallOccurredBeforeFinalAnswer`;
- `AnswerUsesToolEvidence`;
- `NoUnexpectedWriteTool`.

The exact runtime tool names and span attributes must be discovered from a small
instrumented pilot run before finalizing queries. Evaluators should not guess
span names from class names.

### How should deterministic and non-deterministic cases be combined?

Use one framework but distinguish the evaluation mode, evidence, and acceptance
policy for each case.

#### Deterministic cases

Use deterministic evaluators wherever the expected behavior can be expressed in
code:

- routing to a known agent;
- selecting or avoiding a tool;
- validating tool argument JSON;
- preserving an exact URL;
- limiting tool-call count;
- observing a successful tool return;
- returning a Pydantic model or expected result shape;
- staying under a timeout, token, or cost budget;
- refusing to invent knowledge when the controlled store has no answer;
- exact outputs from mocked models and mocked tools.

Appropriate Pydantic Evals primitives include `EqualsExpected`, `Equals`,
`Contains`, `IsInstance`, `MaxDuration`, `HasMatchingSpan`, and custom
`Evaluator` classes.

These cases should use fixed fixtures and mocked boundaries where possible. They
can become hard CI gates after the harness is stable.

#### Non-deterministic cases

Use live models when the property under test is genuinely probabilistic:

- routing from varied natural-language phrasing;
- semantic correctness of a knowledge answer;
- groundedness in retrieved entities and relations;
- quality of entity/relation extraction;
- completeness of an ingestion summary;
- usefulness and clarity of the response;
- semantic quality of generated tool arguments;
- resilience to ambiguous or underspecified prompts.

Use narrow LLM-judge rubrics, one quality dimension per evaluator. For example,
do not ask one judge whether an answer is "good, correct, grounded, concise, and
helpful." Use separate groundedness, answer relevance, and citation-quality
evaluators so a regression is diagnosable.

Judge configuration should:

- include the input whenever relevance or instruction-following is assessed;
- include an expected output only when it is a reference answer rather than an
  exact required string;
- use a low-temperature judge;
- record reasons during the pilot;
- use explicit evaluator names;
- use a judge model chosen independently from the model under test when practical;
- be calibrated against a small human-reviewed set before its score gates changes.

Non-deterministic results should initially be treated as evidence, not binary CI
truth. Run important cases repeatedly and evaluate distributions or pass rates
rather than assuming one run is representative. A reasonable pilot is three runs
per live case while rubrics and thresholds are being calibrated.

#### Hybrid cases

Most useful agent cases should combine both approaches. An ingestion case can
assert deterministically that:

- `@Manager` delegated to `@WebIngest`;
- a web tool was called;
- the exact URL was present in its arguments;
- a knowledge write tool returned successfully;

and use an LLM judge only for:

- whether the extracted entities and relations capture the important content;
- whether the final summary accurately describes what was stored.

This keeps cost and evaluator uncertainty focused on qualities that cannot be
expressed reliably in code.

### Does evaluation need access to Logfire, or does it intercept traffic?

Pydantic Evals runs the task in the evaluation process. It does not query Logfire
to decide what happened, and Logfire does not execute the evaluation.

The flow is:

```text
Dataset case
    │
    ▼
Pydantic Evals task adapter
    │ starts and drives
    ▼
KnowledgeTeam / Akgentic / Pydantic AI
    │ emits OpenTelemetry spans and Akgentic events
    ▼
Evaluators inspect output, metrics, attributes, span tree, and collected events
    │
    ├── local EvaluationReport
    └── optional export to Logfire
```

Pydantic Evals creates an OpenTelemetry trace around each case and captures spans
emitted while its task function is running. Pydantic AI instrumentation emits
model-request and tool-call spans. This is instrumentation, not network traffic
interception.

HTTP instrumentation is a separate choice. Enabling
`logfire.instrument_httpx(capture_all=True)` can capture provider request and
response bodies, but it is not required for normal agent or tool-span evaluation
and may expose prompts, retrieved content, credentials in headers, or other
sensitive data. It should remain off unless there is a specific debugging need
and a reviewed redaction policy.

There are three useful Logfire modes:

1. **Local-only evaluation:** configure the SDK so spans are available to the
   evaluation process but are not exported to Logfire. This is appropriate for
   local deterministic work, CI without credentials, and sensitive cases.
2. **Conditional export:** use `send_to_logfire="if-token-present"`. Developers
   and CI jobs with a token get the Logfire experiment UI; other environments
   still run the evaluation locally.
3. **Dedicated evaluation project:** export live experiments to a Logfire project
   or environment clearly separated from production telemetry, for example
   `knowledge-akgents-evals` and `environment=development` or `ci`.

Logfire is valuable for:

- comparing a candidate experiment with a baseline;
- inspecting failed cases and their trace trees;
- reviewing output, evaluator reasons, duration, token use, and cost;
- turning interesting production traces into future evaluation cases;
- collaborating on datasets and regressions.

It should not be mandatory for all evaluation execution. The code-defined dataset
and evaluators should remain runnable from the repository, and the local report
must remain useful if no `LOGFIRE_TOKEN` is present.

## Approved Phase 0 pilot specification

The first pilot will use two user-provided pages:

- Jettro Coenradie's about page: <https://coenradie.com/about>
- Yuma's background page:
  <https://www.weareyuma.com/en/about/about-us/background>

The pages were reviewed on 2026-09-12. They are suitable for an initial pilot
because they provide:

- two different domains and page structures;
- short factual questions with deterministic answers;
- broader questions that permit valid paraphrasing;
- a realistic ingest-then-query workflow;
- named entities and relations suitable for knowledge-graph verification.

The core suite should not fetch the live pages on every run. During implementation,
capture a reviewed, cleaned fixture from each page and record its source URL and
capture date. The fixed fixture makes regressions reproducible. A separate
external-integration tier can periodically repeat the cases against the live
pages to detect crawler, rendering, or website changes.

### Reviewed source facts

These facts form the initial golden evidence. They should be represented in a
machine-readable fixture when the evaluation suite is implemented.

#### Jettro Coenradie

Source statements include:

- the page title and author identify **Jettro Coenradie**;
- he describes himself as a **software architect and search enthusiast**;
- his work centers on software architecture, search, AI, data, and cloud-native
  development;
- he helps teams turn complex technology into systems people can use and
  maintain.

For the initial questions:

- expected last name: `Coenradie`;
- required profession concept: `software architect`;
- accepted supporting description: `search enthusiast`;
- related specialisms such as search, AI, data, and cloud-native development are
  useful context but do not replace the required profession concept.

#### Yuma

Source statements include:

- Yuma presents itself as **one partner to design, build, and run digital
  transformation**;
- it guides organizations through every stage of the digital-transformation
  journey;
- it connects strategy, design, technology, data, and execution in an end-to-end
  approach;
- it increasingly frames transformation as AI-driven and human-centered;
- it was formed by integrating six specialized companies from Belgium and the
  Netherlands.

The six companies named on the page are:

1. `xplus`
2. `Luminis`
3. `BPSOLUTIONS`
4. `Total Design`
5. `Aprico Consultants`
6. `B12 Consulting`

The page uses both "Aprico Consulting" in a heading and "Aprico Consultants" in
the prose. Evaluation should normalize these as the same company rather than
failing on that wording difference.

### Pilot shape

The pilot contains two stateful scenarios and six logical cases:

```text
Scenario 1: Jettro
  1. Ingest the Jettro about page
  2. Ask: "What is the profession of Jettro Coenradie?"
  3. Ask: "What is the last name of Jettro?"

Scenario 2: Yuma
  4. Ingest the Yuma background page
  5. Ask: "What does Yuma do?"
  6. Ask: "What companies formed Yuma?"
```

Each scenario starts with an empty isolated knowledge store. Its two questions
run only after the corresponding ingestion case has completed successfully.
This intentionally verifies the product's end-to-end promise rather than loading
the expected facts directly into the database.

For diagnosis, the same four questions should later also be available in a
retrieval-only dataset with a pre-seeded knowledge fixture. This separates:

- ingestion or extraction failures;
- storage failures;
- retrieval failures;
- answer-generation failures.

The end-to-end scenarios answer "does the product work?" The retrieval-only
cases answer "which stage failed?"

### Case 1: ingest Jettro's about page

**Input**

- target: manager, unless the first pilot needs to isolate direct ingestion;
- message: a natural request to ingest `https://coenradie.com/about`;
- fixture: reviewed page content captured on 2026-09-12.

**Required deterministic behavior**

- the manager delegates to `@WebIngest`;
- the web retrieval tool is called;
- the requested URL is exactly the Jettro about URL after harmless URL
  normalization such as a trailing slash;
- a knowledge-graph write operation occurs after retrieval;
- all required tool calls return successfully;
- the final response reaches the human;
- the final response states that content was stored rather than pretending only
  to summarize the page.

**Stored-knowledge checks**

- an entity representing Jettro Coenradie exists;
- the stored data links him to the profession `software architect`;
- `search enthusiast` is stored as a description, role, interest, or equivalent
  relation;
- the surname is not lost through incorrect name splitting.

**Non-deterministic quality check**

- the stored entity/relation set captures the central professional facts without
  adding unsupported biographical claims.

### Case 2: profession of Jettro Coenradie

**Question**

`What is the profession of Jettro Coenradie?`

**Required deterministic behavior**

- the manager delegates to `@Knowledge`;
- the knowledge search tool is called;
- no knowledge write operation occurs;
- the answer contains the normalized concept `software architect`;
- the response reaches the human successfully.

**Allowed variation**

The answer may also call him a search enthusiast or mention his work in search,
AI, data, and cloud-native development. An answer that only says "IT consultant,"
"AI expert," or another broader approximation should not pass unless it also
states that he is a software architect.

**Evaluation type**

- deterministic required-concept assertion;
- deterministic routing and tool-use assertions;
- optional relevance score later, but no LLM judge is needed for the first pilot.

### Case 3: last name of Jettro

**Question**

`What is the last name of Jettro?`

**Required deterministic behavior**

- the manager delegates to `@Knowledge`;
- the knowledge search tool is called;
- no write operation occurs;
- the normalized answer contains exactly the surname `Coenradie`;
- no other surname is proposed.

**Evaluation type**

- deterministic entity-value assertion;
- deterministic routing and tool-use assertions.

This case should remain intentionally simple. It proves that a precise fact
survives ingestion, storage, retrieval, and answer generation.

### Case 4: ingest Yuma's background page

**Input**

- target: manager;
- message: a natural request to ingest the Yuma background URL and focus on what
  Yuma does and which companies formed it;
- fixture: reviewed page content captured on 2026-09-12.

**Required deterministic behavior**

- the manager delegates to `@WebIngest`;
- the web retrieval tool receives the exact Yuma URL;
- the knowledge update tool runs after retrieval;
- required tool calls return successfully;
- the response reaches the human and reports stored knowledge.

**Stored-knowledge checks**

- a Yuma entity exists;
- Yuma is related to digital transformation or an equivalent normalized concept;
- all six founding/forming companies are present;
- the six companies are related to Yuma as constituent, integrated, founding, or
  equivalent source organizations;
- Belgian and Dutch origin may be stored, but should not be required in the first
  pilot.

**Non-deterministic quality check**

- the graph captures Yuma's end-to-end role and company composition while
  avoiding navigation, cookie-banner, or marketing-boilerplate entities.

The last condition is particularly useful because the live Yuma page contains a
large cookie declaration and extensive site-wide content. The fixed fixture
should retain enough of this noise to verify extraction quality, while still
being reviewed and safe to store in the repository.

### Case 5: what Yuma does

**Question**

`What does Yuma do?`

**Required concepts**

The answer must communicate that Yuma is a unified/end-to-end partner for digital
transformation. Strong answers explain that it helps organizations design, build,
and run transformation by connecting strategy, design, technology, data, and
execution.

**Required deterministic behavior**

- the manager delegates to `@Knowledge`;
- the knowledge search tool is called;
- no knowledge write operation occurs;
- the answer mentions digital transformation;
- the response reaches the human.

**Non-deterministic quality checks**

- the answer accurately summarizes Yuma's role rather than listing unrelated
  individual services;
- it is grounded only in the ingested page;
- it does not overstate Yuma as solely an AI company, cloud company, or software
  development company;
- a concise answer is acceptable and preferred.

**Evaluation type**

- deterministic routing, tool-use, and required-topic assertions;
- one narrow LLM judge for semantic accuracy and groundedness;
- optional completeness score for the design/build/run or end-to-end concept.

### Case 6: companies that formed Yuma

**Question**

`What companies formed Yuma?`

**Expected normalized set**

```text
xplus
Luminis
BPSOLUTIONS
Total Design
Aprico Consultants
B12 Consulting
```

**Required deterministic behavior**

- the manager delegates to `@Knowledge`;
- the knowledge search tool is called;
- no write operation occurs;
- all six normalized company names appear in the answer;
- no unsupported seventh company is included;
- the response reaches the human.

**Normalization rules**

- comparison is case-insensitive;
- punctuation and harmless whitespace differences are ignored;
- `Aprico Consulting` and `Aprico Consultants` are equivalent;
- `B12` alone is insufficient unless the answer elsewhere makes clear that it
  means `B12 Consulting`;
- `BPSOLUTIONS` may be rendered with different capitalization.

**Evaluation type**

- deterministic set recall: all six companies are present;
- deterministic set precision: no additional company is claimed to have formed
  Yuma;
- deterministic routing and tool-use assertions;
- no LLM judge is needed unless answers repeatedly use forms that are difficult
  to normalize reliably.

### Initial pilot metrics

Record these metrics without making all of them release gates:

- routing correctness per case;
- required-tool-call success;
- unexpected-tool-call count;
- tool argument validity;
- tool return success;
- end-to-end completion;
- final-answer correctness;
- total duration;
- model request count;
- tool-call count;
- input and output tokens;
- estimated cost;
- groundedness score for the two broader ingestion/purpose checks.

The first pilot is successful when:

- all six cases complete and can be diagnosed from their structured execution
  record;
- the two exact-answer cases pass deterministically;
- the six-company answer is evaluated without an LLM judge;
- tool arguments can be inspected as parsed data;
- each tool call can be correlated with its return;
- ingestion and query routing are visible;
- the broader Yuma answer can be judged with a focused, reviewable rubric;
- repeated runs reveal whether the main variance comes from ingestion, retrieval,
  answer generation, or the evaluator.

## Proposed evaluation architecture

### 1. A typed case input

Define a Pydantic model for inputs rather than using unstructured strings. It
should represent:

- user message;
- optional direct target such as `Knowledge` or `WebIngest`;
- fixture or knowledge-base seed identifier;
- execution mode, such as mocked, recorded, or live;
- expected timeout;
- optional model configuration override;
- optional tags such as `routing`, `retrieval`, `ingestion`, or `regression`.

Do not put expected behavior in this input model. Expected agent, tools, argument
constraints, answer facts, and quality criteria belong in expected output,
metadata, or case-specific evaluators.

### 2. A structured task output

The task adapter should not return only the final answer. It should return a
Pydantic model containing enough evidence for deterministic evaluation:

- final user-visible answer;
- ordered actor messages;
- ordered tool calls with parsed arguments;
- correlated tool returns and success flags;
- participating agents;
- completion reason;
- elapsed duration;
- any surfaced exception or timeout;
- identifiers needed to correlate relevant spans or events.

The final answer can still be passed to LLM judges, while custom evaluators can
inspect the structured execution record.

### 3. An evaluation-specific team runner

`KnowledgeTeam.send()` is fire-and-forget and the application currently streams
results through a browser-oriented callback. The evaluation harness therefore
needs a small adapter that:

1. starts an isolated team;
2. subscribes an evaluation event collector;
3. sends one case's message;
4. waits for a well-defined completion event or final message;
5. enforces a timeout;
6. assembles the structured task output;
7. shuts down the actor system in all outcomes.

Completion detection must be designed explicitly. Sleeping for a fixed duration
would make evaluations slow and flaky. The preferred signal is a final message
addressed to `@Human`, correlated with the current case/run. If Akgentic exposes a
stronger run-completion event, use it. Otherwise the adapter can combine a final
human-directed message with a short event-queue quiet period.

This runner belongs under `evals/tasks/` unless creating it reveals a generally
useful application API. Production code should not import Pydantic Evals.

### 4. Per-case isolation

The current agents share a `#VectorStore` and `knowledge_graph` collection. Cases
must not leak knowledge into one another.

Use Pydantic Evals `CaseLifecycle` to:

- create or select a clean store before each case;
- load only the fixture data required by that case;
- create fake web responses or controlled documents;
- start the team after instrumentation and fixture setup;
- shut down the team and clean resources afterward;
- retain failed-case diagnostics only when explicitly enabled.

Initially run agent cases with `max_concurrency=1`. The actor system, environment
configuration, and shared vector-store naming make concurrent case isolation
uncertain. Concurrency can be increased only after each case has a unique store or
collection namespace and no process-global state is shared.

### 5. Two observation channels

Enable Logfire and Pydantic AI instrumentation before constructing the
`KnowledgeTeam`, because its inner Pydantic AI agents are created during team
startup.

Capture:

- Pydantic AI/OpenTelemetry spans for model requests, tool execution, latency,
  token use, cost, and exceptions;
- raw Akgentic events for manager delegation, inter-agent messages, tool-call
  arguments, tool-return correlation, and the user-visible final message.

Where the same fact exists in both channels, prefer the stable semantic source:

- use Akgentic message events for actor routing;
- use raw `ToolCallEvent` fields for exact argument checks;
- use Pydantic AI spans for duration, provider/model activity, and tool execution
  traces;
- use the structured task output for final-answer evaluators.

## Initial dataset design

Start with 12-20 carefully chosen cases, not a large generated benchmark. Each
case should represent a product requirement, known failure mode, or meaningful
decision boundary.

### Dataset A: routing

Examples:

- a normal stored-knowledge question delegates to `@Knowledge`;
- "please learn from this URL" delegates to `@WebIngest`;
- a direct `@Knowledge` target bypasses manager routing;
- a direct `@WebIngest` target preserves the URL and focus;
- an ambiguous request produces a reasonable route without both specialists
  doing unnecessary work;
- a question containing a URL but asking about already stored knowledge tests
  the intended routing policy explicitly.

Primary evaluators:

- expected recipient;
- forbidden recipient;
- agent participation count;
- maximum delegation count;
- final response reaches the human.

### Dataset B: knowledge retrieval

Use a small fixed knowledge graph with facts that are easy to inspect.

Examples:

- answerable single-fact question;
- answer requiring two related entities;
- question with irrelevant entities in the store;
- absent information;
- conflicting or stale facts if the storage model permits them;
- request that attempts to make the agent answer from general model knowledge.

Primary evaluators:

- knowledge search was called;
- no write-enabled behavior occurred;
- returned answer includes required facts;
- absent knowledge is acknowledged;
- no unsupported factual claims;
- entity/relation citations are present and correspond to retrieved evidence;
- groundedness judge for cases where wording is flexible.

### Dataset C: web ingestion

Avoid relying on arbitrary live websites for the core suite. Serve fixed HTML or
stub the web retrieval boundary so source content is reproducible.

Examples:

- one page with three clear entities and relations;
- page with navigation and boilerplate noise;
- page with no useful knowledge;
- invalid or unreachable URL;
- duplicate URL ingestion;
- URL plus a narrow extraction focus;
- content containing instructions that should be treated as page data rather
  than agent instructions.

Primary evaluators:

- web retrieval tool called with the exact URL;
- crawl/fetch mode is appropriate for the case;
- knowledge update tool called only after content retrieval;
- required argument fields are present and valid;
- all tool calls returned successfully, or failure is clearly reported;
- stored graph contains expected core entities and relations;
- final summary matches what was actually stored;
- no fabricated entities beyond the supplied document.

### Dataset D: end-to-end ingest then query

These cases test the central product promise: information ingested by
`@WebIngest` becomes queryable by `@Knowledge`.

Each case should:

1. start with an empty isolated store;
2. ingest a controlled document;
3. verify the expected knowledge was written;
4. ask a question in a second turn;
5. verify the answer uses the newly stored knowledge.

This dataset should remain small because it is slower and has more possible
failure points. Its value is high because it detects broken integration between
tools that isolated tests cannot catch.

### Dataset E: resilience and regressions

Add cases whenever a real failure is found:

- malformed tool arguments followed by a successful retry;
- tool timeout;
- tool returns no results;
- specialist fails to answer;
- excessive or repeated tool calls;
- manager fails to relay the specialist's answer;
- prompt regression causing direct, ungrounded answering;
- unsafe write-tool use during a read-only question.

Regression cases should include a short metadata field explaining the original
failure and the invariant being protected.

## Evaluation policy

### Evaluator hierarchy

Prefer evaluators in this order:

1. exact deterministic assertions;
2. custom structural or domain checks;
3. span/event-based behavioral checks;
4. semantic algorithms if they have a validated threshold;
5. LLM judges for genuinely subjective properties;
6. human review for calibration and disputed cases.

An LLM judge should never be used to check exact tool names, exact URLs, JSON
validity, call counts, return success, or other facts already present in the
execution record.

### Scores versus assertions

Use assertions for non-negotiable contracts:

- correct routing;
- required tool call;
- no write tool in read-only cases;
- valid arguments;
- successful completion;
- no timeout.

Use numeric scores for qualities with a continuum:

- groundedness;
- extraction coverage;
- answer relevance;
- conciseness;
- citation quality.

Do not combine all metrics into one opaque score initially. Separate dimensions
make regressions explainable and let the team decide which trade-offs matter.

### Thresholds

Do not invent thresholds before collecting baseline data.

For the pilot:

- deterministic contract assertions should target 100%;
- live-model quality metrics should be observed over repeated runs;
- latency, tokens, and cost should be recorded but not gated;
- LLM-judge agreement should be compared with human labels;
- cases with evaluator disagreement should be reviewed and used to refine the
  rubric or replace the judge with deterministic logic.

After calibration, define thresholds per dataset rather than one global number.
For example, a routing smoke suite may require 100%, while a difficult extraction
quality score may use a lower threshold plus "no critical regression" rules.

## Execution tiers

### Tier 1: conventional tests

Run on every change:

- existing unit tests;
- direct tool tests with fakes;
- tool schema/contract tests;
- custom evaluator unit tests;
- event collector and task-output assembly tests.

No model, network, Qdrant service, Logfire token, or LLM judge should be required.

### Tier 2: deterministic evaluation smoke suite

Run on pull requests once stable:

- a small subset of evaluation cases;
- mocked or controlled model responses;
- controlled tool fixtures;
- local-only telemetry;
- sequential execution.

This verifies the evaluation harness and behavioral contracts without introducing
model variance or API cost.

### Tier 3: live candidate evaluation

Run manually, before significant prompt/model/tool releases, or on a schedule:

- real configured model;
- controlled local documents and isolated store;
- deterministic evaluators plus selected LLM judges;
- conditional or required Logfire export;
- experiment metadata including commit, branch, model, prompt version, and
  evaluation configuration;
- comparison against a named baseline experiment.

### Tier 4: limited external integration evaluation

Run less frequently:

- real Tavily/web access;
- real Qdrant deployment;
- explicitly allow-listed, stable URLs;
- conservative concurrency and retries;
- no hard CI gate until upstream variance is understood.

External integration results should be distinguished from agent-quality results.
A web outage must not be reported as proof that the routing prompt regressed.

## Logfire and data-governance plan

Use a dedicated Logfire project or at least a dedicated service name and
environment for evaluations. Stable dataset names should group related experiments,
while experiment names should describe the candidate, such as
`routing-prompt-v2` or `knowledge-tool-schema-v3`.

Before sending evaluation data:

- classify whether prompts, retrieved documents, and outputs may contain secrets,
  personal data, or licensed/private content;
- avoid using production customer content in the initial dataset;
- redact secrets and authorization headers;
- keep full HTTP body capture disabled by default;
- ensure tokens are supplied through environment or Logfire configuration and
  never stored in datasets;
- decide retention and access rules for evaluation traces.

The initial source of truth should be version-controlled datasets in this
repository. Logfire can receive experiments and synchronized copies for browsing.
Hosted Logfire datasets can be considered later if collaborative curation or
promotion of production traces becomes more important than code review of every
case.

## Rollout plan

### Phase 0: define success criteria

Before writing the harness:

- choose the first product behavior to protect, preferably manager routing plus
  one knowledge query and one web-ingestion scenario;
- identify which assertions are strict contracts and which are quality scores;
- define the maximum acceptable cost and duration for a pilot run;
- decide which content is safe to send to Logfire.

Deliverable: a short evaluation specification for 3-5 pilot cases.

### Phase 1: prove observability

Create a one-case experimental runner that starts instrumentation before
`KnowledgeTeam`, sends one controlled request, and records:

- the Pydantic Evals span tree;
- Pydantic AI model/tool spans;
- Akgentic sent-message events;
- raw `ToolCallEvent` and `ToolReturnEvent` data;
- the final human-directed response.

Inspect the actual span names and attributes in both a local dump and Logfire.
Confirm whether Akgentic's wrapped Pydantic AI agents are fully visible through
global instrumentation. Identify any actor-level gaps that require custom spans.

Exit criteria:

- one complete case has a stable completion signal;
- tool arguments and returns can be correlated;
- manager-to-specialist routing is visible;
- no sensitive HTTP payloads are captured unintentionally.

#### Phase 1 findings (2026-09-12)

The first isolated live spike used the Jettro about page, the configured
`gpt-5.6-luna` model, Tavily, an in-memory vector store, and no Logfire export.

Observed result:

- the scenario completed successfully in approximately 30 seconds;
- four actor messages captured the complete route:
  `@Human -> @Manager -> @WebIngest -> @Manager -> @Human`;
- three tool calls were captured:
  `team_activity`, `web_fetch_tool`, and `update_graph`;
- all tool-call arguments were valid JSON;
- all three tool calls had matching successful `ToolReturnEvent` records;
- the final human-directed answer correctly reported that Jettro Coenradie was
  stored as a software architect and search enthusiast;
- no actor errors were observed;
- the persistent Qdrant configuration was overridden, so the spike used an
  isolated in-memory store.

The Pydantic Evals case span tree contained zero child spans. A no-network control
experiment that ran a Pydantic AI `TestModel` directly inside a Pydantic Evals
task captured the expected `invoke_agent` and model-chat spans. This confirms
that Logfire and Pydantic Evals instrumentation are working, but the active
OpenTelemetry context is not propagated from the evaluation task into Akgentic's
actor worker threads.

Consequences:

- Akgentic events are immediately suitable for routing, tool-name, tool-argument,
  ordering, correlation, success, and final-response evaluations.
- `HasMatchingSpan` cannot currently evaluate the inner Akgentic agent/tool run
  as part of the Pydantic Evals case trace.
- Pydantic AI may still emit independent traces when Logfire export is enabled,
  but detached traces are less useful because they cannot be evaluated through
  the case's `ctx.span_tree` or opened as one connected experiment trace.
- Phase 2 can proceed with an event-first design without blocking on tracing.
- Trace-context propagation should be handled as a separate integration task,
  ideally in the Akgentic actor/message boundary rather than through
  evaluation-only monkey-patching.

The Phase 1 implementation now provides:

- an explicit `pydantic-evals[logfire]` evaluation dependency group;
- `evals/observability_spike.py` with one Jettro ingestion case;
- opt-in Logfire export;
- a guard against accidental writes to persistent Qdrant;
- structured capture of actor messages, raw parsed tool arguments, correlated
  tool returns, errors, completion reason, and final response;
- focused tests for argument parsing, call/return correlation, final-response
  detection, and actor-error handling.

The first fixed-fixture Phase 2 run also showed that `team_activity` is optional:
the manager can route directly to `@WebIngest` without calling that helper. It
must therefore remain an observed metric rather than a required tool assertion.
The stable ingestion contract is the ordered actor route plus successful
`web_fetch_tool` and `update_graph` calls.

After correcting that assertion, the fixed-fixture ingestion case passed 100% of
its deterministic checks in 17.1 seconds. It observed:

- the complete four-message route from human to manager to web-ingest and back;
- `web_fetch_tool` called with the exact source URL and a focused extraction
  query;
- `update_graph` called with entities for Jettro Coenradie, Software Architect,
  and Search Enthusiast;
- explicit relations linking Jettro Coenradie to both professional concepts;
- valid JSON arguments and successful correlated returns for both tools;
- a final response containing `Jettro Coenradie` and `software architect`;
- no actor errors and no writes to persistent Qdrant.

The first three-turn Jettro scenario then completed in 43.5 seconds and produced
all three expected human responses. Both retrieval questions routed through
`@Knowledge`, each called `search_graph`, and the answers contained `Software
Architect` and `Coenradie` respectively.

That run also exposed a separate framework-level behavior: the manager called
`hire_members` with an empty `roles` list, and its matching `ToolReturnEvent`
reported `success=false`. The call did not affect the correct outcome, while
every domain tool (`web_fetch_tool`, `update_graph`, and both `search_graph`
calls) returned successfully. Domain-tool success is therefore the strict
assertion; empty, failed, or uncorrelated framework-management calls are retained
as separate diagnostic metrics for later efficiency and framework evaluation.

After applying that distinction, the approved rerun passed 100% of its
deterministic assertions in 44.8 seconds. It captured the expected 12-message
route, three human responses, one fixture-backed `web_fetch_tool` call, one
`update_graph` call, and two `search_graph` calls. All five calls had successful
correlated returns, with zero parse errors, actor errors, uncorrelated calls, or
empty `hire_members` calls. The earlier empty `hire_members` behavior is
therefore nondeterministic rather than a stable part of this scenario's
contract, but remains observable through the diagnostic metrics.

The next fixed-fixture scenario applies the same three-turn contract to Yuma:

1. ingest the reviewed background-page fixture;
2. ask what Yuma does;
3. ask which companies formed Yuma.

The deterministic answer checks require the concepts `digital`,
`transformation`, and `partner`, followed by all six company names: xplus,
Luminis, BPSOLUTIONS, Total Design, Aprico, and B12 Consulting. Checking the
stable token `Aprico` intentionally normalizes the source variants `Aprico
Consulting` and `Aprico Consultants` without weakening the other company-name
checks.

The first approved Yuma run passed 100% of its deterministic assertions in 48.5
seconds. It captured the expected 12-message route and three human responses.
The answers described Yuma as an end-to-end digital transformation partner and
named xplus, Luminis, BPSOLUTIONS, Total Design, Aprico Consultants, and B12
Consulting. All eight observed tool calls had successful returns, with no
argument parse errors, actor errors, uncorrelated calls, or empty
`hire_members` calls. The knowledge agent made three `search_graph` calls: one
for the first question and two for the company question. This satisfies the
correctness contract while providing a useful baseline for later tool-efficiency
evaluation.

A retrieval-only dataset now contains the same four pilot questions as
independent cases. Each case starts a fresh team and injects a reviewed local
knowledge fixture through a `search_graph` tool that uses Akgentic's real
`SearchQuery` input schema and production-style result formatting. This avoids
depending on unsupported mutation of the actor-owned graph while preserving the
model-facing retrieval contract.

These cases require the normal
`@Human -> @Manager -> @Knowledge -> @Manager -> @Human` route, at least one
successful `search_graph` call, the case-specific answer terms, and no
`web_fetch_tool` or `update_graph` calls. They isolate routing, query generation,
tool invocation, use of retrieved context, and answer generation from web
retrieval, extraction, and graph writes. The fixture search itself is deliberately
simple token matching; production retrieval quality remains covered by the
end-to-end scenarios rather than being simulated here.

The first approved retrieval-only run passed 100% of the deterministic
assertions across all four cases, averaging 13.3 seconds per case. Every case
completed with the expected four-message route, used at least one successfully
correlated `search_graph` call, avoided `web_fetch_tool` and `update_graph`, and
returned all required answer terms. There were no tool-argument parse errors,
actor errors, uncorrelated calls, or empty `hire_members` calls. The runner's
compact JSON output was subsequently generalized to include every report case
rather than only the first; this reporting-only correction did not require
another paid run.

The deterministic foundation also includes negative controls proving that an
incorrect route, an answer produced from a fixture missing the required fact,
and an ingestion-tool call in a retrieval-only case each fail their intended
evaluator. A task-lifecycle isolation test runs two cases sequentially and
verifies that each receives a distinct `KnowledgeTeam` instance and that both
actor systems are shut down, preventing shared in-memory graph state between
cases.

### Phase 2: build the deterministic foundation

**Status: complete.** The pilot now has fixed web and knowledge fixtures,
event-based evaluators, isolated case lifecycle, successful Jettro and Yuma
end-to-end baselines, four retrieval-only cases, and negative controls for
route, grounding, forbidden-tool, and state-isolation failures.

Implement:

- typed input, metadata, and task-output models;
- the evaluation event collector;
- isolated case lifecycle;
- deterministic custom evaluators;
- fake web and fixed knowledge fixtures;
- unit tests for each evaluator and collector behavior.

Run sequentially and locally without a Logfire token.

Exit criteria:

- 5-8 deterministic cases produce stable identical assertions across repeated
  runs;
- a deliberately broken fixture or route causes the expected evaluator to fail;
- one case cannot contaminate another.

### Phase 3: add live model behavior

**Status: complete for the pilot.** Canonical and paraphrased retrieval prompts
have been run once with usage capture and three times for variance. Correctness
and routing remained stable; search count, optional management calls, latency,
requests, and tokens showed measurable variance. Cost is represented by raw
usage rather than a potentially inaccurate monetary conversion.

The first Phase 3 increment adds one natural-language paraphrase for each of the
four retrieval-only pilot questions. Canonical and paraphrased cases use the
same reviewed fixture and identical routing, tool, and answer contracts, with a
`prompt_variant` metadata field separating the two groups. This makes
prompt-sensitivity measurable without adding web or storage variability.

The first approved eight-case run passed 100% of all assertions and averaged
12.6 seconds per case. Canonical and paraphrased prompts all followed the
expected route, used only the allowed knowledge path, and produced the required
facts. Seven cases used one `search_graph` call. The paraphrased Yuma-purpose
case used three differently worded searches before returning the same correct
answer. This is the first observed prompt-sensitive variance: outcome quality
and routing were stable, while tool efficiency varied.

The evaluation CLI supports Pydantic Evals' native case repetition through
`--repeat N`, defaults to one execution, rejects values below one, and records
the requested repeat count in experiment metadata. The first variance sample
should use `--repeat 3`, producing 24 sequential executions across the eight
canonical and paraphrased retrieval cases.

The first approved three-repeat sample completed 24 executions with 100% of
deterministic assertions passing and an average duration of 16.2 seconds.
Fifteen executions used one `search_graph` call, eight used two, and one used
three, for 34 searches overall. Three executions (12.5%) also made the
nondeterministic no-op `hire_members(roles=[])` call. Each had a matching return
event with `success=false`; none of the required domain-tool calls failed. The
diagnostics now report failed returns separately from genuinely uncorrelated
calls, and compact JSON labels the per-call boolean `succeeded` rather than the
ambiguous `returned`.

Akgentic's event stream also exposes `LlmUsageEvent`, so the event-first harness
captures per-response model/provider identity, input and output tokens, cache
read/write tokens, and provider request counts without relying on propagated
OpenTelemetry spans. These values are aggregated into Pydantic Evals metrics and
the compact JSON report. Monetary cost is intentionally not inferred in the
harness because the event contains usage but no versioned provider pricing.

The first approved live verification confirmed this path without Logfire or
span propagation. The fixed Jettro ingestion case passed in 27.4 seconds and
emitted six OpenAI `gpt-5.6-luna` response/request records totaling 11,154 input
tokens, 689 output tokens, 8,046 cache-read tokens, and 3,090 cache-write
tokens. All observed tools succeeded. No monetary estimate is recorded because
the model identifier has no authoritative pricing information in the usage
event; adding an assumed price would make the report look more precise than the
available evidence.

The approved eight-case retrieval usage baseline also passed 100% and averaged
17.4 seconds per case. Across the run, the agents emitted 49 model requests,
75,424 input tokens, 3,544 output tokens, 68,285 cache-read tokens, and 6,992
cache-write tokens. The four canonical prompts used 23 requests, 34,379 input
tokens, and five graph searches; their four paraphrases used 26 requests,
41,045 input tokens, and six graph searches.

The largest single-run outlier was the paraphrased Yuma-company question: it
still answered correctly, but used 11 requests, 18,692 input tokens, and two
graph searches, compared with five requests, 8,088 input tokens, and two
searches for the canonical question. This should remain an efficiency signal
rather than a correctness failure until more samples establish a defensible
threshold. One optional empty `hire_members` call again returned
`success=false`; all required retrieval calls succeeded.

Add representative natural-language variants and run them against the real
configured model. Record:

- routing success rate;
- tool selection and argument correctness;
- completion rate;
- duration;
- token usage and estimated cost;
- output-quality scores.

Run each pilot case multiple times. Review all failures and classify each as:

- application defect;
- model variance;
- evaluator defect;
- fixture/environment problem;
- external-provider failure.

Exit criteria:

- the team understands normal variance and cost;
- deterministic contracts remain stable;
- live failures are diagnosable from the trace and execution record.

### Phase 4: calibrate LLM judges

**Status: complete for the pilot.** The two single-property judges match all
human labels in the initial run and across three repeated runs. They remain
opt-in and are not yet release-blocking.

The initial judge-calibration dataset is deliberately separate from live agent
execution. It contains eight static, human-labeled examples balanced between
four passes and four failures. Failure controls cover invented facts,
irrelevant answers, and incomplete lists; one passing case verifies that
`Aprico Consulting` and `Aprico Consultants` are treated as equivalent.

The Pydantic `LLMJudge` sees the question, reviewed evidence, and candidate
answer, but not the human label. Its rubric requires direct relevance, complete
list answers, and support for every factual claim. A dedicated runner compares
the resulting `grounded_and_relevant` assertion with the hidden human label and
reports agreement case by case. Logfire export remains opt-in.

The first approved calibration produced the intended decision for all eight
cases: four human-approved answers passed and four human-rejected answers
failed, including the incomplete company list and the accepted Aprico name
variant. The initial post-report comparison crashed because the Pydantic output
configuration field was named `evaluation_name`, not `name`; all judge calls had
already completed, so no result was lost and no paid rerun was needed. The
runner now uses the correct explicit assertion name and also safely handles a
single default-named judge assertion.

The judge runner supports the same validated `--repeat N` option as the agent
runner. Its JSON summary reports agreement for every execution and aggregates
agreement by original source case, making decision flips visible despite
Pydantic's repeated-case name suffixes.

The approved three-repeat stability run achieved 24/24 agreement with the human
labels. Every source case agreed in all three runs, including invented facts,
the irrelevant surname answer, the incomplete company list, and the accepted
Aprico name variant. The report's raw assertion pass rate is 50% by design
because half of the calibration examples are negative; label agreement is the
relevant calibration measure.

The combined rubric is then split into two single-property judges:

- `groundedness` checks only whether every factual claim is supported, without
  penalizing omissions or irrelevance;
- `answer_relevance` checks whether the question is answered directly and
  completely, without duplicating the factual-support judgment.

Human labels are independent for both dimensions. Thus an invented but direct
profession answer is ungrounded but relevant, while an incomplete company list
is grounded but not complete/relevant. The runner reports agreement overall,
per dimension, and per source case.

The first approved split calibration achieved 16/16 agreement: eight of eight
groundedness decisions and eight of eight answer-relevance decisions matched
the independent human labels. The intended distinctions held for the invented
but direct answers and the supported but incomplete company list. The raw
assertion pass rate was 68.8%, which only reflects how many human labels are
positive across the two dimensions; calibration quality is measured by label
agreement.

The approved three-repeat split calibration achieved 48/48 agreement:
groundedness matched 24/24 human decisions and answer relevance matched 24/24.
Every source case agreed in all three runs, with no decision flips. This meets
the pilot stability criterion, while the small synthetic dataset remains a
reason not to treat the judges as release-blocking yet.

Create a small human-labeled set for groundedness, extraction quality, and answer
relevance. Compare judge output and reasons with those labels.

Refine rubrics until:

- each rubric measures one named property;
- judge disagreements are understood;
- repeated judge runs are sufficiently stable;
- thresholds reflect observed data rather than intuition.

Do not make judge scores release-blocking before this calibration.

### Phase 5: operationalize

**Status: locally complete; hosted CI deferred.** Stable Make targets,
deterministic tests, report persistence, baseline comparison, safety defaults,
and opt-in Logfire export are available. Hosted CI depends on making the
editable sibling Akgentic dependency reproducible.

The repository now exposes Make targets for deterministic harness tests, each
fixed-fixture live scenario, the canonical/paraphrased retrieval suite, the
three-repeat variance sample, and one-shot or repeated judge calibration.
`EVAL_FLAGS` carries explicit options such as `--send-to-logfire`, and
`EVAL_TIMEOUT` controls actor wait time. All agent-evaluation targets force
`AKGENTIC_QDRANT_URL=''`; paid execution remains an explicit developer action.

There is currently no GitHub Actions workflow. A generic hosted workflow would
not be reproducible because `akgentic-llm` resolves from the editable sibling
path `../akgentic-llm`. CI integration is therefore deferred until that
dependency is published or the workflow deliberately checks out the sibling
repository. Once available, `make test-evals` is the deterministic no-network
gate; paid agent and judge evaluations should remain manual or scheduled.

Both runners can persist reports through `--save-report PATH` and render a
candidate against a prior native Pydantic Evals report through
`--baseline PATH`. Generated files belong under the gitignored
`eval-reports/` directory because they may contain prompts, answers, fixture
paths, and tool arguments. Stable conclusions and thresholds belong in source
control; raw execution reports do not.

Add documented commands for:

- deterministic local evaluation;
- a selected live dataset;
- a full scheduled experiment;
- optional Logfire export;
- baseline/candidate comparison.

Introduce CI gradually:

- hard-gate deterministic evaluator and harness tests;
- hard-gate only proven stable live assertions;
- publish but do not initially gate subjective score changes;
- alert on task errors, major cost increases, and clear deterministic regressions.

### Phase 6: grow from failures

The first negative-control regression asks for Jettro Coenradie's favorite
database. The fixture contains Jettro but no fact about a preferred database,
so retrieval still returns related context while the agent must resist filling
the missing attribute from inference or model memory. The case requires a
successful knowledge search, an explicit statement that the fact is unavailable
or unspecified, and a suggestion to ingest a source; web fetch and graph update
remain forbidden.

The event runner accepts `--case NAME`, allowing a newly added regression case
to be verified without rerunning every paid case in its dataset.

The first live run correctly refused to invent a favorite database, but scored
90.9% because it did not suggest ingestion. It also made five graph searches,
including a retry query seeded with guessed database names. This is classified
as an application prompt-adherence and efficiency defect, not an evaluator
failure. The Knowledge-agent prompt now starts with one targeted search,
prohibits guessed answer candidates in retry queries, and requires an explicit
ingestion recommendation when a fact is absent. The regression permits at most
two searches.

The first rerun reduced the behavior to one targeted search and lowered input
usage from 9,711 to 7,535 tokens, but the final response still omitted the
ingestion recommendation. It also used the valid phrase "does not state", which
the initial accepted-term list had missed. The evaluator now accepts that
wording, the Knowledge prompt requires the exact next step "Please ingest a
source via @WebIngest.", and the Manager prompt explicitly preserves that
recommendation when relaying a missing-fact response.

The final approved rerun passed 100% in 18.3 seconds. It used two
non-speculative `search_graph` calls, stated that the knowledge base did not
contain the favorite-database fact, avoided inventing an answer, and explicitly
asked for a relevant source URL for `@WebIngest`. All tool calls succeeded. This
is the pilot's first complete evaluation-driven product correction: the failing
case was retained, the application behavior was fixed, and the same case proved
the fix.

Treat the dataset as a product artifact:

- add a case for every meaningful production or development failure;
- keep case names stable so experiments compare cleanly;
- review obsolete cases instead of silently weakening evaluators;
- separate coverage changes from quality changes;
- periodically remove duplicate cases that add cost without new information.

## Proposed dependency and command strategy

The deferred real-Qdrant evaluation investigation and continuation checklist
are recorded in [`qdrant-evals-follow-up.md`](qdrant-evals-follow-up.md). That
document also records the intended later migration from the current temporary
Python tool-injection seams to catalog-defined production and evaluation team
profiles.

When implementation starts, declare evaluation dependencies explicitly even
though they are currently installed transitively through `pydantic-ai`:

```toml
[dependency-groups]
eval = [
    "pydantic-evals[logfire]",
]
```

Pinning should remain compatible with the Pydantic AI version selected by
Akgentic. Pydantic Evals and Pydantic AI currently share version 2.43.0 in the
lockfile, which reduces compatibility risk, but the project should not rely on
an undeclared transitive package.

Suggested commands:

```text
make test                 conventional deterministic tests
make eval-smoke           controlled deterministic evaluation cases
make eval-live            selected real-model cases
make eval-full            comprehensive/scheduled experiment
```

The commands should make cost and external requirements obvious. A developer
should never trigger a paid live evaluation by running the ordinary test suite.

## Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Fire-and-forget actor API | Flaky completion and partial outputs | Build an event-driven runner with explicit timeout and completion detection |
| Shared vector store | Cases influence one another | Per-case store/collection isolation and sequential execution initially |
| Assumed span names | Behavioral evaluators pass or fail incorrectly after upgrades | Discover real spans in Phase 1 and unit-test query logic |
| Framework version drift | Akgentic and Pydantic Evals instrumentation diverge | Declare versions explicitly and rerun the observability proof on upgrades |
| LLM judge variance | Noisy release decisions | Human calibration, low temperature, repeated runs, narrow rubrics |
| External web variance | False application regressions | Fixed web fixtures for core suites; separate external-integration tier |
| Evaluation cost | Suites become too expensive to run | Deterministic-first design, small live subsets, concurrency and budget limits |
| Sensitive trace content | Prompts or documents leave the environment | Dedicated project, redaction policy, no HTTP body capture by default |
| Evaluator overfitting | Scores improve without product improvement | Preserve diverse cases, inspect regressions, and periodically review with humans |
| One aggregate score | Important failures are hidden by averages | Keep routing, groundedness, tool correctness, latency, and cost separate |

## Decision checkpoint after the pilot

Pydantic Evals should be adopted as the standard evaluation framework if the
pilot demonstrates all of the following:

- the `KnowledgeTeam` can be driven as one reliable task per case;
- Pydantic AI spans expose useful model and tool execution details;
- Akgentic events provide stable actor routing and raw tool arguments;
- custom evaluators are straightforward to maintain;
- Logfire makes baseline/candidate comparison materially easier;
- local execution remains useful without Logfire access;
- the framework does not force evaluation logic into production code;
- live-run cost and duration are acceptable.

Reconsider or supplement it if:

- actor execution cannot be correlated reliably with evaluation cases;
- required tool arguments or returns are unavailable from both spans and events;
- the team needs offline trace evaluation from a different telemetry store rather
  than in-process task execution;
- dataset governance requires an independent service immediately;
- another framework provides substantially better support for Akgentic's actor
  model with less custom adaptation.

Based on the current code and dependencies, none of these blockers is apparent.
The main unknown is the exact quality of the spans produced through Akgentic's
Pydantic AI wrapper, which is why proving observability is the first technical
phase rather than assuming it.

## Sources

- Pydantic Evals overview:
  <https://pydantic.dev/docs/ai/evals/evals/>
- Built-in evaluators:
  <https://pydantic.dev/docs/ai/evals/evaluators/built-in/>
- Custom evaluators:
  <https://pydantic.dev/docs/ai/evals/evaluators/custom/>
- Span-based evaluation:
  <https://pydantic.dev/docs/ai/evals/evaluators/span-based/>
- LLM-as-a-judge:
  <https://pydantic.dev/docs/ai/evals/evaluators/llm-judge/>
- Dataset management:
  <https://pydantic.dev/docs/ai/evals/how-to/dataset-management/>
- Case lifecycle:
  <https://pydantic.dev/docs/ai/evals/how-to/lifecycle/>
- Metrics and attributes:
  <https://pydantic.dev/docs/ai/evals/how-to/metrics-attributes/>
- Concurrency:
  <https://pydantic.dev/docs/ai/evals/how-to/concurrency/>
- Logfire integration:
  <https://pydantic.dev/docs/ai/evals/how-to/logfire-integration/>
- Pydantic AI Logfire instrumentation:
  <https://pydantic.dev/docs/ai/integrations/logfire/>
- Logfire datasets and experiments:
  <https://pydantic.dev/docs/logfire/evaluate/evals/>
- Reviewing and comparing Logfire experiments:
  <https://pydantic.dev/docs/logfire/evaluate/review-experiments/>
