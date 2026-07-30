---
name: defect-interpretation
description: Explain deterministic lattice defect classifications from registered graph and CT analysis results. Use when asked why a strut or node is missing, thin, thick, uncertain, or disconnected.
---

# Defect Interpretation

1. Call `inspect_element` for the selected or requested element.
2. Explain status through recorded material support, skeleton support, thickness,
   rule thresholds, and boundary/registration warnings.
3. Call `compare_expected_geometry` for a selected strut when expected-versus-CT
   context is requested.
4. Treat detector labels as evidence-backed candidates; rule strength is not a
   calibrated probability. Do not recalculate or override the classification.

