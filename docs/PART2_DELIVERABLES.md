# Part 2: Registered Missing-Strut Inspection

This project implements the **Visual Reasoner / Autonomous Data Explorer** track for the aligned 0.5% missing-strut CT specimen. It separates the workflow into bounded roles:

1. `missing_strut_inspector` validates the coordinate-system constraint and runs the deterministic screen.
2. `analyze_missing_struts.py` samples CT intensity along all 18,468 expected, registered strut centrelines and selects a transparent threshold from representative CT slices.
3. A reviewer (human or agent) inspects the saved diagnostics and candidate table before making any defect claim.

Run from the repository root:

```powershell
C:\Users\waliu\anaconda3\python.exe src/analyze_missing_struts.py
```

The authoritative, sensitivity-checked run is under `output/part2/refined_registration_20260728/`:

- `tube_r2/inspection_summary.json` - retained radius-2 operating point and candidate totals.
- `tube_r2/threshold_candidates.csv` and `tube_r2/threshold_diagnostics.png` - threshold evidence.
- `tube_r2/strut_candidates.csv` - one traceable screening record per registered strut.
- `NDE_refinement_readout.md` - tube-radius sensitivity and the no-confirmation conclusion.

The deliberately unregistered STL files are excluded. Candidate labels are not confirmed defects: the radius/threshold sensitivity is too large to make a quantitative defect claim without independent registration landmarks or blinded CT-neighborhood adjudication.
