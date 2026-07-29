"""Traceable Part 2 inspection of a registered octet-lattice CT scan.

The graph must already be in CT voxel coordinates.  This script deliberately
does not attempt STL registration; it measures the CT intensity along each
expected strut centreline and produces *candidates* for human review.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
import numpy as np
import tifffile
from skimage.filters import threshold_otsu

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _paths(metadata: dict, samples: int, shape: tuple[int, int, int]):
    nodes = {row["id"]: np.asarray(row["position"], dtype=float) for row in metadata["junctions"]}
    records, requests = [], {}
    for strut in metadata["struts"]:
        start, end = nodes[strut["junction0"]], nodes[strut["junction1"]]
        points = start + np.linspace(0.08, 0.92, samples)[:, None] * (end - start)
        xyz = np.rint(points).astype(int)
        valid = ((xyz[:, 0] >= 0) & (xyz[:, 0] < shape[2]) & (xyz[:, 1] >= 0)
                 & (xyz[:, 1] < shape[1]) & (xyz[:, 2] >= 0) & (xyz[:, 2] < shape[0]))
        index = len(records)
        records.append({"id": strut["id"], "midpoint": (start + end) / 2, "values": np.full(samples, np.nan)})
        for sample_index, (x, y, z) in enumerate(xyz[valid]):
            requests.setdefault(int(z), []).append((index, sample_index, int(y), int(x)))
    return records, requests


def run(tiff_path: Path, metadata_path: Path, output_dir: Path, samples: int = 31, tube_radius: int = 2, missing_fraction: float = .04, disconnected_fraction: float = .35, disconnected_gap: int = 8) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with tifffile.TiffFile(tiff_path) as tif:
        shape = (len(tif.pages), *tif.pages[0].shape)
        records, requests = _paths(metadata, samples, shape)
        representative = [int(round(x)) for x in np.linspace(shape[0] * .15, shape[0] * .85, 7)]
        images = [tif.pages[z].asarray() for z in representative]
        otsu_values = [float(threshold_otsu(image)) for image in images]
        base_threshold = float(np.median(otsu_values))
        for z, entries in requests.items():
            image = tif.pages[z].asarray()
            for record_index, sample_index, y, x in entries:
                # A small local tube is substantially less sensitive to a one-voxel
                # registration offset than a single centreline voxel. The 75th
                # percentile preserves strut support without allowing one hot voxel
                # to turn a fully empty cross-section into material.
                patch = image[max(0, y - tube_radius) : y + tube_radius + 1, max(0, x - tube_radius) : x + tube_radius + 1]
                records[record_index]["values"][sample_index] = np.percentile(patch, 75)

    all_values = np.concatenate([r["values"][np.isfinite(r["values"])] for r in records])
    thresholds = sorted({int(round(base_threshold * factor)) for factor in (.90, .96, 1.00, 1.04, 1.10)})
    candidates = []
    for threshold in thresholds:
        fractions = np.array([np.mean(np.nan_to_num(r["values"] >= threshold, nan=False)) for r in records])
        # A useful operating point retains most well-built struts, while not
        # collapsing the lower-intensity missing/broken candidates into clear.
        separation = float(np.percentile(fractions, 75) - np.percentile(fractions, 10))
        candidates.append({"threshold": threshold, "median_centerline_fraction": float(np.median(fractions)),
                           "clear_fraction": float(np.mean(fractions >= .60)), "separation": separation})
    eligible = [row for row in candidates if row["median_centerline_fraction"] >= .60]
    selected = max(eligible or candidates, key=lambda row: (row["separation"], row["threshold"]))
    threshold = int(selected["threshold"])

    results = []
    for record in records:
        present = np.nan_to_num(record["values"] >= threshold, nan=False)
        gap_lengths = [len(part) for part in "".join("1" if v else "0" for v in present).split("1")]
        longest_gap = max(gap_lengths, default=0)
        fraction = float(present.mean())
        # Conservative labels: intermediate cases remain review candidates instead
        # of inflating missing/disconnected totals.
        flag = "missing_candidate" if fraction < missing_fraction else ("disconnected_candidate" if fraction < disconnected_fraction and longest_gap >= disconnected_gap else ("uncertain_candidate" if fraction < .60 else "clear"))
        x, y, z = record["midpoint"]
        results.append({"strut_id": record["id"], "material_fraction": fraction, "longest_gap_samples": longest_gap,
                        "flag": flag, "x_voxel": float(x), "y_voxel": float(y), "z_voxel": float(z)})
    counts = {flag: sum(row["flag"] == flag for row in results) for flag in ("missing_candidate", "disconnected_candidate", "uncertain_candidate", "clear")}

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "strut_candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
    with (output_dir / "threshold_candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candidates[0])); writer.writeheader(); writer.writerows(candidates)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].hist(all_values, bins=100, color="#496a85"); axes[0].axvline(threshold, color="#c94c4c", label=f"selected: {threshold}")
    axes[0].set(title="Registered centreline intensities", xlabel="CT intensity", ylabel="sample count"); axes[0].legend()
    axes[1].bar([r["threshold"] for r in candidates], [r["separation"] for r in candidates], color="#496a85")
    axes[1].axvline(threshold, color="#c94c4c"); axes[1].set(title="Threshold candidate separation", xlabel="threshold", ylabel="75th - 10th percentile fraction")
    fig.tight_layout(); fig.savefig(output_dir / "threshold_diagnostics.png", dpi=180); plt.close(fig)
    summary = {"pipeline": "registered-centreline-screen-v1", "input_tiff": str(tiff_path), "registered_graph": str(metadata_path),
               "volume_shape_zyx": shape, "samples_per_strut": samples, "representative_otsu_thresholds": otsu_values,
               "selected_threshold": threshold, "threshold_rationale": "Maximized centreline-fraction separation among candidates retaining median fraction >= 0.60.",
               "counts": counts, "tube_radius_voxels": tube_radius, "classification": {"missing_fraction_lt": .04, "disconnected_fraction_lt": .35, "disconnected_gap_gte": 8, "uncertain_fraction_lt": .60}, "limitation": "Candidates are not confirmed defects; inspect CT neighborhoods before claiming missing or disconnected struts. 0% baseline calibration is unavailable because its TIFF is not present locally."}
    (output_dir / "inspection_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "README.md").write_text("# Registered missing-strut inspection\n\nThis conservative run samples a 2-voxel local tube around aligned expected centrelines. Strong missing/disconnected labels are deliberately stricter; intermediate low-support struts are retained as `uncertain_candidate` for CT-neighbourhood review. `strut_candidates.csv` is not ground truth. The STL is intentionally excluded because it is not registered to this CT volume.\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiff", type=Path, default=Path("data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"))
    parser.add_argument("--metadata", type=Path, default=Path("data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"))
    parser.add_argument("--output", type=Path, default=Path("output/part2/refined_registration_20260728/tube_r2"))
    parser.add_argument("--samples", type=int, default=31)
    parser.add_argument("--tube-radius", type=int, default=2)
    parser.add_argument("--missing-fraction", type=float, default=.04)
    parser.add_argument("--disconnected-fraction", type=float, default=.35)
    parser.add_argument("--disconnected-gap", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(run(args.tiff, args.metadata, args.output, args.samples, args.tube_radius, args.missing_fraction, args.disconnected_fraction, args.disconnected_gap), indent=2))
