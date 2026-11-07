# Phase 8 — investigation quality evaluation

The offline scorer and report-bound review workflow are implemented. Visual/mobile QA
was explicitly deferred by the user on 2026-11-07 and does not block this milestone.

## What is measured

| Metric | Definition |
|---|---|
| Citation validity | The report passes the existing shape/UUID membership checks; this is not semantic support |
| Finding support rate | Reviewer-labelled supported findings / all findings |
| Citation support precision | Reviewer-approved finding/evidence pairs / all unique cited pairs |
| Expected fact coverage | Expected facts linked to at least one supported finding / all expected facts |

The `investigation-review-v1` gate requires every finding and cited pair to be supported,
at least 80% expected fact coverage, a supported summary, adequate uncertainty and no
unsafe suggestions. An inconclusive review fails the gate rather than becoming an
invented accuracy score. Duplicate citations cannot inflate the denominator or numerator.
The thresholds are initial review-policy choices, not calibrated accuracy guarantees.
Invalid reports fail before semantic scoring. Reports without annotations return
`review_required` and null semantic metrics, even when all IDs are valid.

Review hashes bind the exact question, report and complete retrieved evidence including
provenance. Changing a claim, source excerpt, ID or question invalidates the review.
The evaluation `artifact_sha256` is distinct from the workflow approval `report_sha256`.
Provenance shape is validated locally; this tool does not independently fetch original
sources or establish export authenticity. Use trusted exports and compare original logs.
Reviewer identity/kind is operator-supplied metadata, not an authenticated attestation.
This evaluator does not approve, publish, modify or reject the operational investigation.

## Offline benchmark

```powershell
.venv/Scripts/python.exe -m scripts.evaluate_investigations benchmark
```

Fourteen hand-constructed synthetic cases cover valid observations, invented IDs,
irrelevant existing citations, fabricated root causes, partly supported citation sets,
missing facts, weak uncertainty, unsafe suggestions, unsupported summaries, inconclusive
and absent reviews, duplicate references and instruction-like source text. The CLI exits
nonzero if any expected gate outcome changes; the same command runs in GitHub CI.
It also compares all results with the checked-in fixture/hash/metric baseline, so score
changes cannot silently pass just because their final pass/fail classification is unchanged.

All 14 expected outcomes match. This measures scorer mechanics against fixture labels.
It does **not** measure OpenAI accuracy, prove prompt-injection robustness, establish
general report quality or independently validate the fixture author's judgements.

## Review a saved report without model credits

Use a JSON export from the workspace, or the CLI status result containing `question`,
`report` and `evidence`. Input JSON is bounded to 256 KiB.

```powershell
.venv/Scripts/python.exe -m scripts.evaluate_investigations template --report '<report.json>'
.venv/Scripts/python.exe -m scripts.evaluate_investigations score --report '<report.json>'
```

The template is saved in ignored `.cache/evaluations/`, keyed by artifact hash. Existing
templates are not overwritten. The supplied saved report was structurally valid with
two findings and four unique cited pairs; semantic support remains unreviewed. A private
template was generated without changing the report or spending credits.

To complete the review:

1. Read the question and source evidence, and define expected facts before judging the
   candidate's findings. Avoid defining an easier reference answer after reading the report.
2. Fill in `reviewer.name`; keep `kind` as `human`. For each finding index choose
   `supported`, `unsupported` or `uncertain` (reviewer cannot establish support).
3. Add only cited event IDs whose actual text supports the whole finding to `supported_by`.
   Unsupported/inconclusive findings must have an empty support list. Similar vocabulary
   or chronology alone does not prove causation. Preserve unknown source timezones.
4. Add unique `expected_facts`, each with its text and `covered_by` finding indices. Facts
   linked only to unsupported findings do not count as covered. Leave absent facts' lists empty.
5. Set `summary_supported`, `uncertainty_adequate` and `unsafe_suggestions` to actual booleans.
   Check summary claims independently and treat instructions embedded in logs as untrusted data.

```powershell
.venv/Scripts/python.exe -m scripts.evaluate_investigations score --report '<report.json>' --review '<private-review.json>' --check
```

`--check` exits nonzero for a failing or unreviewed report. An unfinished template is
rejected. Output contains scores, hashes and fixed reasons, not source text or reviewer
names. Real reports/reviews remain private; only synthetic fixtures and regression results
belong in Git. No inference, embedding, database access or checkpoint mutation occurs.

Independent human labels on a larger, representative set of real reports are still
needed before claiming a live-model quality baseline. Inter-reviewer agreement and
dependency/runtime version migrations are outside this initial evaluation slice.
