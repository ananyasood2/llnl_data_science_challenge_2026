# Part 2: Coordinated Missing-Strut Pipeline

## Scope and orchestration

This implementation is a staged multi-agent workflow, not a flat tool collection. The bounded agent definitions are in `.codex/agents/`; their durable handoffs are the metadata, screening, visual-review, and repair artifacts below `output/part2/`. The complete operating contract is in [MULTI_AGENT_PIPELINE.md](MULTI_AGENT_PIPELINE.md).

| Stage | Durable output | Rule |
| --- | --- | --- |
| Data explorer | `output/part2/metadata/inventory.{json,md}` | Determines registration status before any comparison. |
| Detector | `output/part2/refined_registration_20260728/tube_r2/` | Samples an aligned TIFF along expected JSON strut centrelines. |
| Visual reasoner | `output/part2/visual_repair/registered_candidates.png` | Reviews a rendered, colour-coded registered graph. |
| Repair/solver | `output/part2/visual_repair/repaired_graph.*` | Restores candidates in a non-destructive graph proposal and estimates a proxy metric. |
| Dashboard/co-pilot | `apps/web/` | Reads saved JSON artifacts through local routes; it does not fabricate pipeline results. |

## Dataset inventory and registration

The saved inventory found one available CT stack: the 0.5% nominal specimen 1 TIFF, `761 x 815 x 837` `uint16` voxels. It has one matching registered JSON graph in CT voxel coordinates (`18,468` struts and `10,206` junctions). The nominal design graph and all four STL variants (`0%`, `0.1%`, `0.5%`, and `1%`) are unregistered and were excluded from direct CT comparison.

The repository documentation names additional scan variants, but they are not present locally. Therefore this run reports a measured screen only for the registered 0.5% pair. The full inventory, including file counts and caveats, is [inventory.md](../output/part2/metadata/inventory.md).

## Literature grounding

The detection interpretation is grounded in Tran et al., *NDT & E International* 138 (2023), [DOI 10.1016/j.ndteint.2023.102870](https://doi.org/10.1016/j.ndteint.2023.102870). It motivates treating missing and disconnected struts as separate classes and treating the nominal removal percentage as a design label rather than a strict measured result. The inventory records that measured missing percentage may exceed nominal and that disconnected behavior varies by specimen.

## Registered 0.5% screening run

**Authoritative current run:** `output/part2/refined_registration_20260728/tube_r2/`. This conservative run uses a two-voxel tube sample and reserves intermediate support for `uncertain_candidate`. The radius-1 and radius-3 repeats are retained beside it as sensitivity evidence.

| Final robust screening result | Count |
| --- | ---: |
| Missing candidate | 1,049 |
| Disconnected candidate | 5,262 |
| Uncertain candidate | 1,083 |
| Clear | 11,074 |
| Strong flagged total | 6,311 (34.17%) |

`src/analyze_missing_struts.py` reads TIFF pages lazily, samples 31 points along each expected registered centreline, and selects a threshold from seven representative Otsu measurements. The retained radius-2 threshold is `39725`; evidence is retained in `threshold_candidates.csv` and `threshold_diagnostics.png`.

| Screening result | Count | Interpretation |
| --- | ---: | --- |
| Missing candidate | 1,049 | Very low centreline material support; requires neighbourhood review. |
| Disconnected candidate | 5,262 | Low support with a long internal gap; requires neighbourhood review. |
| Uncertain candidate | 1,083 | Intermediate support; retained for review only. |
| Clear | 11,074 | Did not meet the candidate rules. |
| Expected struts | 18,468 | Registered graph total. |

The `7,394` review candidates (`40.03%`) exceed the nominal 0.5% design label. This is not a measured missing-strut rate and must not be reported as one: it includes disconnected/intermediate candidates and threshold/segmentation artifacts. The sensitivity readout records **zero confirmed missing struts**. Per-strut evidence is in [strut_candidates.csv](../output/part2/refined_registration_20260728/tube_r2/strut_candidates.csv).

## Historical visual review and repair scenario

The repair artifacts below are retained as a historical candidate-screen scenario. They are not derived from the authoritative sensitivity-checked run and must not be used to propose physical repair.

The visual stage saved reusable 3D renders: [candidate view](../output/part2/visual_repair_robust_v2/registered_candidates.png) and [repair view](../output/part2/visual_repair_robust_v2/repaired_graph.png). Candidate classes are colour-coded and the repair is saved as an annotated [repaired graph](../output/part2/visual_repair_robust_v2/repaired_graph.json).

The repair proposal restores only `6,311` strong missing/disconnected candidate edges and excludes uncertain candidates. It is deliberately an upper-bound scenario, not a manufacturing recommendation, because the candidate set is not confirmed.

| Metric | Screened graph | Repaired proposal |
| --- | ---: | ---: |
| Relative-density proxy | `1.2404e-05` | `2.2170e-05` |
| Normalized stiffness proxy | `0.313` | `1.000` |
| Estimated proxy recovery | - | `68.70%` |

This is explicitly **not FEA**. It is a traceable lightweight comparator; the assumption and caveat are retained in [repair_summary.json](../output/part2/visual_repair/repair_summary.json).

## Dashboard and grounded co-pilot

Run `npm run dev:web` and open the local dashboard. It provides TIFF/JSON/combined inspection views, candidate filtering, direct manipulation, and a co-pilot. The dashboard and co-pilot read the authoritative `refined_registration_20260728/tube_r2/inspection_summary.json` together with inventory/repair context; every response lists its source artifact. Large TIFF voxels are never sent to the browser.

## Evaluation

The rubric is [rubric_missing_struts.md](../evals/rubric_missing_struts.md). The scored registered 0.5% run is [evaluation_missing_struts_registered_0point5dash1.json](../evals/evaluation_missing_struts_registered_0point5dash1.json): workflow evidence maturity is `3.67/5`. Accuracy is intentionally `null`, because no registered per-strut ground-truth labels are available for a valid precision/recall computation. The next step is blinded CT-neighbourhood adjudication or a registered truth join, then class-specific precision, recall, F1, and a confusion matrix.
