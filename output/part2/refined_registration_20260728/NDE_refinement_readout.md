# 0.5%-missing octet lattice: registered CT refinement readout

## Decision

**No struts are confirmed missing from this run.** The supplied TIFF/JSON pair is registered, and the unregistered STL was not opened or used. However, the screening result is not stable under the requested tube-radius/segmentation changes: the best-performing radius still produces a candidate rate orders of magnitude above the nominal 0.5% condition. That behavior is evidence of residual registration/segmentation/partial-volume uncertainty, not evidence for thousands of missing struts.

## Inputs and coordinate constraint

- CT: `data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif` (ZYX = 761 x 815 x 837, uint16)
- Design: `data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json` (10,206 junctions; 18,468 struts)
- Coordinate handling: graph XYZ sampled in CT XYZ/ZYX indexing; no STL geometry used.

The JSON includes locations but no explicit transform/covariance or independent registration landmarks. Therefore no further rigid/deformable transform can be defensibly estimated and persisted from the provided graph alone; its supplied registration is retained. This is the registration limitation that blocks quantitative defect confirmation.

## Centerline/tube sensitivity

All runs used 31 samples per strut, endpoint trimming from 8% to 92%, local 75th-percentile tube support, seven representative-slice Otsu values, and a threshold selected by separation while retaining median centerline support >= 0.60.

| tube radius (voxels) | selected threshold | missing candidates | disconnected candidates | uncertain candidates | clear |
|---:|---:|---:|---:|---:|---:|
| 1 | 39,725 | 1,217 | 5,614 | 1,199 | 10,438 |
| 2 | 39,725 | 1,049 | 5,262 | 1,083 | 11,074 |
| 3 | 42,017 | 1,159 | 6,505 | 1,384 | 9,420 |

Radius 2 is retained only as the least-flagging operating point (60.0% clear). It is **not** a validated missing-strut count. The threshold candidates for this run span 34,377--42,017; separation improves monotonically but clear fraction falls from 83.4% to 49.6%, showing the material sensitivity directly.

## Classification and recommended follow-up

- Confirmed missing struts: **0** (none can be established from the available evidence).
- Uncertain candidates: **7,394** at the retained radius-2 screen (1,049 low-support plus 5,262 discontinuity plus 1,083 intermediate-support candidates). These are review targets, not defect labels.
- Strongest visual/geometric evidence: use the radius-2 threshold diagnostic and per-strut coordinates below; screen results are sensitive enough that visual CT-neighborhood adjudication or independently registered landmarks are required before confirming defects.

## Audit artifacts

- `tube_r2/inspection_summary.json` -- provenance, selected threshold, rules, and counts.
- `tube_r2/strut_candidates.csv` -- every expected strut with centerline material fraction, longest gap, and registered CT midpoint.
- `tube_r2/threshold_candidates.csv` and `tube_r2/threshold_diagnostics.png` -- segmentation/threshold validation evidence.
- `tube_r1/` and `tube_r3/` -- tube-radius sensitivity repeats.

The older bounded segmentation-distance sensitivity output is retained at `../registered_screen_20260728/` as supplemental evidence, but it likewise did not establish confirmation (selected r=4, threshold 37,026, with 1,975 image-derived flags). No result was constrained to the approximately 92 nominal removals.
