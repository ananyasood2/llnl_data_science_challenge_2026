"""Create a traceable nominal-versus-registered graph comparison artifact."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
NOMINAL = ROOT / "data/missing_struts/octet_truss_9x9x9.json"
REGISTERED = ROOT / "data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
CANDIDATES = ROOT / "output/part2/registered_0point5dash1_robust_v2/strut_candidates.csv"
SCALE = ROOT / "data/missing_struts/physical_scale.json"
OUTPUT = ROOT / "output/part2/graph_comparison"


def run() -> dict:
    nominal = json.loads(NOMINAL.read_text(encoding="utf-8"))
    registered = json.loads(REGISTERED.read_text(encoding="utf-8"))
    scale = json.loads(SCALE.read_text(encoding="utf-8"))["voxel_size_mm"]
    candidate_rows = {int(row["strut_id"]): row for row in csv.DictReader(CANDIDATES.open(encoding="utf-8"))}
    nominal_nodes = {node["id"]: node for node in nominal["junctions"]}
    registered_nodes = {node["id"]: node for node in registered["junctions"]}
    nominal_struts = {strut["id"]: strut for strut in nominal["struts"]}
    registered_struts = {strut["id"]: strut for strut in registered["struts"]}
    if nominal_nodes.keys() != registered_nodes.keys() or nominal_struts.keys() != registered_struts.keys():
        raise ValueError("Nominal and registered graphs do not share the same ID domains.")
    endpoint_mismatches = [sid for sid, strut in nominal_struts.items() if (strut["junction0"], strut["junction1"]) != (registered_struts[sid]["junction0"], registered_struts[sid]["junction1"])]
    thickness_mismatches = [sid for sid, strut in nominal_struts.items() if strut.get("thickness") != registered_struts[sid].get("thickness")]
    design_xyz = np.asarray([nominal_nodes[i]["position"] for i in sorted(nominal_nodes)], float)
    voxel_xyz = np.asarray([registered_nodes[i]["position"] for i in sorted(registered_nodes)], float)
    design_augmented = np.c_[design_xyz, np.ones(len(design_xyz))]
    transform, *_ = np.linalg.lstsq(design_augmented, voxel_xyz, rcond=None)
    residual = voxel_xyz - design_augmented @ transform
    enriched_nodes = [{**registered_nodes[i], "nominal_id": i, "nominal_position": nominal_nodes[i]["position"], "registered_voxel_position": registered_nodes[i]["position"], "registered_position_mm": [value * scale for value in registered_nodes[i]["position"]]} for i in sorted(registered_nodes)]
    enriched_struts = []
    for sid in sorted(registered_struts):
        design = nominal_struts[sid]
        measured = candidate_rows.get(sid, {})
        enriched_struts.append({**registered_struts[sid], "nominal_id": sid, "nominal_junction0": design["junction0"], "nominal_junction1": design["junction1"], "nominal_thickness": design.get("thickness"), "registered_thickness": registered_struts[sid].get("thickness"), "ct_material_fraction": float(measured["material_fraction"]) if measured else None, "ct_longest_gap_samples": int(measured["longest_gap_samples"]) if measured else None, "ct_screening_flag": measured.get("flag")})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": "registered-graph-comparison-v1", "nominal_graph": str(NOMINAL.relative_to(ROOT)), "registered_graph": str(REGISTERED.relative_to(ROOT)), "candidate_measurements": str(CANDIDATES.relative_to(ROOT)), "counts": {"junctions": len(enriched_nodes), "struts": len(enriched_struts), "candidate_rows": len(candidate_rows)}, "id_comparison": {"junction_id_sets_match": True, "strut_id_sets_match": True, "endpoint_mismatch_count": len(endpoint_mismatches), "thickness_mismatch_count": len(thickness_mismatches)}, "position_comparison": {"registered_coordinate_system": "CT voxel", "voxel_size_mm": scale, "least_squares_design_to_voxel_affine_4x3": transform.tolist(), "registration_residual_voxel_rms": float(np.sqrt(np.mean(residual**2))), "registration_residual_voxel_max": float(np.abs(residual).max())}, "thickness_note": "Graph thickness is nominal design metadata (0.1 graph units). Per-strut measured CT diameter is not available in the current screening output."}
    (OUTPUT / "comparison_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUTPUT / "registered_graph_enriched.json").write_text(json.dumps({"junctions": enriched_nodes, "struts": enriched_struts, "unit_cells": registered["unit_cells"], "comparison_summary": report}, separators=(",", ":")), encoding="utf-8")
    (OUTPUT / "README.md").write_text("# Registered graph comparison\n\n`registered_graph_enriched.json` is a derived artifact. It preserves registered IDs and positions, adds nominal ID/position/thickness fields, registered mm coordinates, and CT screening measurements. It does not overwrite either original graph.\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
