# Missing-Strut Pipeline Evaluation Rubric

## Scope

This rubric evaluates a pipeline run against artifacts it actually produced. It is **not** an accuracy score unless hidden or released per-strut ground-truth labels are supplied and joined to the same registered coordinate frame.

The dataset documentation and Tran et al., *NDT&E International* 138 (2023) 102870 provide context that missing-strut rates can exceed nominal design percentages and disconnected struts occur. They do not provide a hidden-label match in this repository for the evaluated run.

## Scored criteria (0-5 each)

| Criterion | 0 | 3 | 5 |
| --- | --- | --- | --- |
| Provenance and registration | No input provenance or unregistered design treated as aligned | Inputs named but alignment evidence incomplete | CT and graph paths, dimensions, and explicit registration status recorded; unregistered STL excluded |
| Detection traceability | Counts only | Per-strut results or threshold table exists | Per-strut records, thresholds, rationale, diagnostics, and reproducible command/output path exist |
| Candidate-label discipline | Candidates reported as confirmed defects | Limitation noted but mixed terminology | Every automated flag remains a candidate pending CT-neighborhood/ground-truth validation |
| Threshold behavior | Arbitrary or undocumented threshold | Candidate sweep saved | Selection criterion is recorded and its trade-offs can be inspected |
| Validation readiness | No path to assess accuracy | Nominal-rate comparison only | Explicit plan for registered hidden-label join, precision/recall/F1, and visual adjudication |
| Visual/repair/dashboard evidence | No reusable downstream assets | Some static assets | Saved rendered review, repair comparison, and grounded dashboard citations |

## Accuracy scoring when labels become available

Join adjudicated or released truth to `strut_id` in the registered graph. Score missing and disconnected classes separately with precision, recall, F1, confusion matrices, and percentage error against both measured and nominal rates. Exclude unmatched IDs and report their count. Do not use nominal percentage as a substitute for per-strut truth.

## Overall interpretation

Average the six criterion scores. This is a workflow-evidence maturity score, not defect-detection accuracy. A run cannot receive an accuracy claim without a verified truth join.
