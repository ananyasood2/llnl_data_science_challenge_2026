# Registered Visual Reasoning and Repair

Run from the repository root:

```powershell
python src/visualize_repair_registered_graph.py
```

The stage consumes only the registered `0point5dash1` JSON graph and the Part 2 candidate CSV. It creates:

- `registered_candidates.png`: full registered design graph with colored candidate overlays.
- `repaired_graph.png`: repaired graph with restored candidate edges in green.
- `repaired_graph.json`: original registered graph plus `repair_status` for every strut.
- `repair_summary.json`: counts, inputs, render paths, and an explicitly non-FEA relative-density/stiffness proxy.

Candidate labels remain screening results rather than confirmed missing/disconnected defects. The repair conservatively records every flagged candidate as restored for comparison, so its metric is an upper-bound scenario until visual CT validation. No STL is read or aligned by this stage.
