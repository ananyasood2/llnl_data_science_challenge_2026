"""Render and repair the registered 0.5% lattice candidate screen.

This intentionally uses the registered JSON coordinate system only.  It does
not attempt to align any STL, and the structural result is a geometry-based
proxy, not an FEA result.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = ROOT / "data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
DEFAULT_CANDIDATES = ROOT / "output/part2/registered_0point5dash1_robust_v2/strut_candidates.csv"
DEFAULT_OUTPUT = ROOT / "output/part2/visual_repair_robust_v2"
DEFECT_FLAGS = {"missing_candidate", "disconnected_candidate"}
COLORS = {"missing_candidate": "#e74c3c", "disconnected_candidate": "#f39c12"}


def load_candidates(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {int(row["strut_id"]): row for row in rows}


def segments(graph: dict) -> tuple[np.ndarray, dict[int, int], np.ndarray]:
    positions = {int(row["id"]): np.asarray(row["position"], dtype=float) for row in graph["junctions"]}
    edge_ids = np.asarray([int(edge["id"]) for edge in graph["struts"]])
    lines = np.asarray([[positions[int(edge["junction0"])], positions[int(edge["junction1"])] ] for edge in graph["struts"]], dtype=float)
    index = {edge_id: i for i, edge_id in enumerate(edge_ids)}
    lengths = np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1)
    return lines, index, lengths


def setup_axes(lines: np.ndarray, title: str):
    figure = plt.figure(figsize=(11, 9), dpi=150)
    axis = figure.add_subplot(111, projection="3d")
    mins, maxs = lines.reshape(-1, 3).min(axis=0), lines.reshape(-1, 3).max(axis=0)
    centre, span = (mins + maxs) / 2, max(maxs - mins)
    for setter, value in zip((axis.set_xlim, axis.set_ylim, axis.set_zlim), centre):
        setter(value - span / 2, value + span / 2)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=21, azim=-53)
    axis.set_title(title, pad=20, fontsize=14)
    axis.set_xlabel("X voxel"); axis.set_ylabel("Y voxel"); axis.set_zlabel("Z voxel")
    return figure, axis


def render_before(lines: np.ndarray, edge_index: dict[int, int], candidates: dict[int, dict[str, str]], output: Path):
    fig, ax = setup_axes(lines, "Registered CT comparison: defect candidates")
    ax.add_collection3d(Line3DCollection(lines, colors="#b7bec6", linewidths=.18, alpha=.22))
    handles = []
    for flag, colour in COLORS.items():
        ids = [sid for sid, row in candidates.items() if row.get("flag") == flag and sid in edge_index]
        if not ids:
            continue
        selected = lines[[edge_index[sid] for sid in ids]]
        # Fine lines keep the dense candidate overlay legible; marker sample is capped for load/readability.
        ax.add_collection3d(Line3DCollection(selected, colors=colour, linewidths=.45, alpha=.72))
        mids = selected.mean(axis=1)
        sample = mids[::max(1, len(mids) // 700)]
        handle = ax.scatter(sample[:, 0], sample[:, 1], sample[:, 2], s=4, c=colour, label=f"{flag.replace('_candidate', '')} ({len(ids)})")
        handles.append(handle)
    if handles:
        ax.legend(loc="upper left", fontsize=8, frameon=True)
    fig.tight_layout(); fig.savefig(output, bbox_inches="tight"); plt.close(fig)


def render_repaired(lines: np.ndarray, restored_indices: list[int], output: Path):
    fig, ax = setup_axes(lines, "Repaired design graph: restored candidate struts")
    ax.add_collection3d(Line3DCollection(lines, colors="#8b969f", linewidths=.21, alpha=.33))
    if restored_indices:
        restored = lines[restored_indices]
        ax.add_collection3d(Line3DCollection(restored, colors="#18a36b", linewidths=.52, alpha=.82))
        mids = restored.mean(axis=1)
        sample = mids[::max(1, len(mids) // 700)]
        ax.scatter(sample[:, 0], sample[:, 1], sample[:, 2], s=4, c="#18a36b", label=f"restored candidate edges ({len(restored_indices)})")
        ax.legend(loc="upper left", fontsize=8, frameon=True)
    fig.tight_layout(); fig.savefig(output, bbox_inches="tight"); plt.close(fig)


def run(graph_path: Path, candidates_path: Path, output: Path) -> dict:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    candidates = load_candidates(candidates_path)
    lines, edge_index, lengths = segments(graph)
    candidate_ids = [sid for sid, row in candidates.items() if row.get("flag") in DEFECT_FLAGS and sid in edge_index]
    restored_indices = [edge_index[sid] for sid in candidate_ids]
    counts = Counter(row.get("flag", "unknown") for row in candidates.values())
    # Cylindrical strut material proxy. Graph thickness is treated as diameter in the supplied metadata.
    diameters = np.asarray([float(edge.get("thickness", .1)) for edge in graph["struts"]])
    material = np.pi * (diameters / 2) ** 2 * lengths
    bounds = lines.reshape(-1, 3)
    volume = float(np.prod(bounds.max(axis=0) - bounds.min(axis=0)))
    intact_volume = float(material.sum())
    removed_volume = float(material[restored_indices].sum()) if restored_indices else 0.0
    before_density = (intact_volume - removed_volume) / volume
    after_density = intact_volume / volume
    # Gibson-Ashby-style scaling used solely as a comparative stiffness proxy.
    before_stiffness = (before_density / after_density) ** 2 if after_density else 0.0
    summary = {
        "stage": "visual-repair-v1",
        "coordinate_system": "registered JSON voxel coordinates",
        "inputs": {"registered_graph": str(graph_path.relative_to(ROOT)), "candidate_csv": str(candidates_path.relative_to(ROOT))},
        "graph": {"junction_count": len(graph["junctions"]), "strut_count": len(graph["struts"])},
        "candidate_counts": dict(sorted(counts.items())),
        "repair": {"restored_candidate_strut_count": len(candidate_ids), "restored_strut_ids": candidate_ids, "repaired_graph": "repaired_graph.json"},
        "mechanics_proxy": {
            "name": "relative-density / stiffness comparison proxy",
            "assumption": "Each graph strut is a cylinder; thickness metadata is interpreted as diameter; normalized stiffness scales with relative density squared.",
            "not_fea": True,
            "before_relative_density": before_density,
            "after_relative_density": after_density,
            "before_normalized_stiffness": before_stiffness,
            "after_normalized_stiffness": 1.0,
            "estimated_stiffness_recovery_percent": (1.0 - before_stiffness) * 100,
        },
        "caveat": "Candidate labels are screening outputs, not confirmed defects. Repair restores only strong missing/disconnected candidates; uncertain candidates are excluded pending CT-neighborhood validation. No unregistered STL was used.",
        "renderings": {"candidate_overlay": "registered_candidates.png", "repaired_overlay": "repaired_graph.png"},
    }
    output.mkdir(parents=True, exist_ok=True)
    repaired = dict(graph)
    repaired["repair_metadata"] = {"candidate_csv": str(candidates_path.relative_to(ROOT)), "restored_candidate_strut_ids": candidate_ids, "caveat": summary["caveat"]}
    repaired["struts"] = [dict(edge, repair_status=("restored_candidate" if int(edge["id"]) in set(candidate_ids) else "retained_design")) for edge in graph["struts"]]
    (output / "repaired_graph.json").write_text(json.dumps(repaired, indent=2), encoding="utf-8")
    (output / "repair_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    render_before(lines, edge_index, candidates, output / "registered_candidates.png")
    render_repaired(lines, restored_indices, output / "repaired_graph.png")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render registered strut candidates and a lightweight repaired design proxy.")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.graph, args.candidates, args.output), indent=2))
