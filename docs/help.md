# Knowledge Akgents documentation

The topic guides below explain how the evaluation harness is organized and how
to extend it.

- [Evaluation architecture](evaluation-architecture/help.md): what is case
  data, what is Knowledge Akgents logic, and what Pydantic Evals provides.
- [Adding evaluation cases](adding-evaluation-cases/help.md): how to add
  retrieval cases and case-specific expectations.
- [Judge calibration](judge-calibration/help.md): when and why to calibrate the
  LLM judges.
- [Running evaluations](running-evaluations/help.md): deterministic checks,
  paid runs, repetitions, reports, and Logfire.
- [Evaluation report viewer](evaluation-report-viewer/help.md): inspect saved
  native reports in a local web interface.
- [Change-aware ingestion](change-aware-ingestion/help.md): how extracted
  content hashes, unchanged skips, commits, failures, and force requests work.
- [Team catalog](team-catalog/help.md): `akgentic-catalog` entries,
  references, runtime bindings, and the Akgentic `TeamCard` boundary.
- [Persistent and selectable teams](persistent-teams/help.md): how catalog
  definitions map to persisted runtime instances, stable Qdrant identity, team
  selection, and the proposed implementation sequence.
- [Actor trace-context propagation](trace-context/help.md): how evaluation,
  OpenTelemetry, model, and tool spans remain connected across local actor
  threads.

The longer-term design and experiment history remain in
[`evals-plan.md`](../evals-plan.md).
