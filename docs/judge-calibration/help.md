# Judge calibration

The live judges assess two independent qualities:

- **groundedness**: factual claims are supported by captured retrieval
  evidence;
- **answer relevance**: the answer directly and completely addresses the
  question.

The rubrics and human-labeled examples are in
`evals/datasets/judge_calibration.py`. The runner is
`evals/runners/judge_calibration.py`.

## What is a rubric?

A rubric is the written set of criteria given to the LLM judge. It explains
what quality the judge should assess and what should cause an answer to pass or
fail.

For example, the groundedness rubric tells the judge to check factual claims
against the supplied evidence, while ignoring completeness and writing style.
The answer-relevance rubric checks whether the question was answered directly
and completely, without deciding whether the answer is factually supported.

A rubric is reusable logic, not case data:

- the **rubric** defines how to judge a quality;
- the **case** supplies a question, evidence, and candidate answer;
- the **human label** records the expected pass or fail decision;
- calibration checks whether the judge applies the rubric consistently with
  that human label.

The current rubrics are the `GROUNDEDNESS_RUBRIC` and
`ANSWER_RELEVANCE_RUBRIC` constants. `evals/evaluators/live.py` reuses those exact
rubrics when evaluating real retrieval answers.

## Why calibration is required

An LLM judge is nondeterministic and can misunderstand a rubric. Calibration
compares its decisions with explicit human labels before the same rubric is
used on real agent output.

Calibration includes representative behavior classes such as:

- correct and supported answers;
- direct but invented answers;
- grounded but incomplete answers;
- irrelevant answers;
- correct missing-knowledge responses;
- hallucinations when knowledge is unavailable;
- generic, unhelpful refusals.

## When to add a calibration case

Do not copy every product evaluation into the calibration dataset. Add a case
when:

- a new judge dimension or rubric is introduced;
- a live result reveals an ambiguous rubric;
- a new class of acceptable or unacceptable answer is not represented;
- a model change causes disagreement with established human labels.

Run calibration once or repeatedly:

```bash
make eval-judge
make eval-judge-stability
```

These commands make paid judge-model calls but do not run the Knowledge team or
its tools.
