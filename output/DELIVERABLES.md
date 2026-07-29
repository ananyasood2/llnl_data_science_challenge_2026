# Part 1 and Part 2 Deliverables

## Part 1 -- unit-cell segmentation and NDE

**Result:** Otsu threshold `0.005813`; foreground fraction `4.2787%`; one skeleton connected component.

- `part1/threshold_optimizer/selection.md` -- threshold decision.
- `part1/threshold_optimizer/threshold_0.004500.npy`, `threshold_0.005813.npy`, and `threshold_0.007000.npy` -- candidate segmentation masks.
- `part1/threshold_optimizer/*_slice_128.png` -- visual comparison for each threshold.
- `part1/unitcell_mask.npy` and `unitcell_skeleton.npy` -- selected segmentation and skeleton.
- `part1/unitcell_raw_slice_128.png` and `unitcell_mask_slice_128.png` -- selected 2D CT/mask evidence.
- `part1/nde_report/nde_report.md`, `view_a.png`, and `view_b.png` -- NDE report and two 3D views.
- `part1/registered_strut_screen/registered_strut_screen.{csv,json}` and comparison PNGs -- registered strut-screen evidence.

## Part 2 -- registered 0.5%-missing lattice inspection

**Authoritative result:** `part2/refined_registration_20260728/`. The analysis confirms **zero missing struts**. The radius-2 run retains 7,394 review candidates, which are not defect confirmations because threshold/tube sensitivity remains high.

- `part2/refined_registration_20260728/NDE_refinement_readout.md` -- decision, limitations, and full sensitivity interpretation.
- `part2/refined_registration_20260728/tube_r2/` -- authoritative candidate table, summary, threshold table, and diagnostic plot.
- `part2/refined_registration_20260728/tube_r1/` and `tube_r3/` -- tube-radius sensitivity repeats.
- `part2/metadata/inventory.{json,md}` -- registered-input inventory.
- `part2/graph_comparison/` -- registered graph metadata/comparison artifacts.

## Historical / supplemental Part 2 outputs

These remain available for audit but are not the active result source:

- `part2/registered_0point5dash1/`, `registered_0point5dash1_review_20260728/`, and `registered_0point5dash1_robust_v2/` -- earlier centreline-screen runs.
- `part2/registered_screen_20260728/` -- segmentation-distance sensitivity, overlay, provenance, and interactive review scene.
- `part2/visual_repair/` and `visual_repair_robust_v2/` -- historical candidate-based repair scenarios; not physical repair recommendations.
