---
name: missing-strut-inspection
description: Run the traceable Part 2 CT/graph workflow to screen an aligned octet lattice for missing or disconnected strut candidates.
---

# Missing-Strut Inspection

Use this skill only with a TIFF and a graph JSON that are already registered to the same voxel coordinate system. Do not combine an unregistered STL with the CT result.

1. Run `python src/analyze_missing_struts.py --tiff <tif> --metadata <registered-json> --output <output-dir>`.
2. Inspect `threshold_diagnostics.png`, `inspection_summary.json`, and the most suspicious rows in `strut_candidates.csv`.
3. Report candidate counts as screening results, not confirmed defect counts. State the selected threshold and the registration limitation.
4. Stop if the JSON is not explicitly registered; report that registration is required before as-designed versus as-built claims.
