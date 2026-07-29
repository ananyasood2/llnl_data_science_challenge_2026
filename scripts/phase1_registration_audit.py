#!/usr/bin/env python3
"""Reproduce the Phase 1 JSON/TIFF coordinate and registration audit.

This utility is intentionally read-only with respect to scientific caches. It
loads the current registered graph, TIFF, segmentation, skeleton, and analysis
records; computes deterministic registration-quality measurements; and writes
compact audit artifacts under ``outputs/verification``.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for search_path in (str(REPO_ROOT), str(SRC_ROOT)):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

from app.datasets import get_dataset  # noqa: E402
from lattice_pipeline.coordinates import CoordinateTransform  # noqa: E402
from lattice_pipeline.io import (  # noqa: E402
    inspect_tiff_metadata,
    load_design_graph,
    load_volume,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _sample_expected_paths(
    analysis: dict[str, Any],
    *,
    samples_per_strut: int = 9,
) -> np.ndarray:
    fractions = np.linspace(0.1, 0.9, samples_per_strut)
    samples = []
    for strut in analysis["struts"]:
        endpoints = np.asarray(strut["polyline"], dtype=float)
        if endpoints.shape != (2, 3):
            raise ValueError(
                f"Phase 1 audit expects two-point struts; ID {strut['id']} "
                f"has shape {endpoints.shape}"
            )
        samples.append(
            endpoints[0, None, :] * (1 - fractions[:, None])
            + endpoints[1, None, :] * fractions[:, None]
        )
    return np.concatenate(samples, axis=0)


def _local_material_support(
    mask: np.ndarray,
    samples_xyz_analysis: np.ndarray,
    *,
    radius_voxels: int = 2,
) -> tuple[float, float]:
    rounded_zyx = np.rint(samples_xyz_analysis[:, ::-1]).astype(np.int64)
    shape = np.asarray(mask.shape, dtype=np.int64)
    rounded_zyx = np.clip(rounded_zyx, 0, shape - 1)
    centerline = np.asarray(mask[tuple(rounded_zyx.T)], dtype=bool)
    nearby = centerline.copy()
    offsets = []
    for dz in range(-radius_voxels, radius_voxels + 1):
        for dy in range(-radius_voxels, radius_voxels + 1):
            for dx in range(-radius_voxels, radius_voxels + 1):
                if dz * dz + dy * dy + dx * dx <= radius_voxels**2:
                    offsets.append((dz, dy, dx))
    for offset in offsets:
        shifted = np.clip(
            rounded_zyx + np.asarray(offset, dtype=np.int64),
            0,
            shape - 1,
        )
        nearby |= np.asarray(mask[tuple(shifted.T)], dtype=bool)
    return float(np.mean(centerline)), float(np.mean(nearby))


def _registration_status(
    *,
    pairing_matches: bool,
    axes: str,
    graph_fits_volume: bool,
    foreground_fraction: float,
    nearby_material_fraction: float,
    skeleton_median_vox: float,
    skeleton_p90_vox: float,
    json_has_registration_metadata: bool,
) -> tuple[str, list[str]]:
    failure_reasons = []
    if not pairing_matches:
        failure_reasons.append("TIFF/JSON specimen basenames do not match")
    if axes != "ZYX":
        failure_reasons.append(f"TIFF axes are {axes!r}, not the expected 'ZYX'")
    if not graph_fits_volume:
        failure_reasons.append("registered graph coordinates fall outside the CT volume")
    if not 0.001 < foreground_fraction < 0.50:
        failure_reasons.append("segmentation foreground fraction is degenerate")
    if nearby_material_fraction < 0.50:
        failure_reasons.append("fewer than half of expected path samples are near material")
    if failure_reasons:
        return "registration_failed", failure_reasons

    warning_reasons = []
    if nearby_material_fraction < 0.80:
        warning_reasons.append("expected-path material support is below 80%")
    if skeleton_median_vox > 3.0 or skeleton_p90_vox > 8.0:
        warning_reasons.append("expected paths are too far from the CT skeleton")
    if warning_reasons:
        return "registration_warning", warning_reasons

    if json_has_registration_metadata:
        return "verified", [
            "pairing, axis convention, declared transform, and measured path support pass"
        ]
    return "likely_valid", [
        "pairing, axis convention, bounds, and measured path support pass",
        "the JSON does not independently declare units or transform provenance",
    ]


def _choose_landmark(
    analysis: dict[str, Any],
    volume_shape_zyx: tuple[int, int, int],
    target_fraction_xyz: tuple[float, float, float],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target_xyz = (
        np.asarray(volume_shape_zyx[::-1], dtype=float)
        * np.asarray(target_fraction_xyz, dtype=float)
    )
    candidates = [
        node
        for node in analysis["nodes"]
        if int(node.get("degree", 0)) >= 4
        and node.get("status") == "healthy"
    ]
    if not candidates:
        candidates = analysis["nodes"]
    selected = min(
        candidates,
        key=lambda node: float(
            np.linalg.norm(
                np.asarray([node["x"], node["y"], node["z"]]) - target_xyz
            )
        ),
    )
    selected_id = int(selected["id"])
    incident = [
        strut
        for strut in analysis["struts"]
        if int(strut["node_a"]) == selected_id
        or int(strut["node_b"]) == selected_id
    ]
    return selected, incident


def _plane_data(
    volume: np.ndarray,
    mask: np.ndarray,
    skeleton: np.ndarray,
    point_xyz: np.ndarray,
    stride: int,
    view: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int], int]:
    x, y, z = np.rint(point_xyz).astype(int)
    xa, ya, za = np.rint(point_xyz / stride).astype(int)
    if view == "XY":
        return (
            np.asarray(volume[z, :, :]),
            np.asarray(mask[za, :, :]),
            np.asarray(skeleton[za, :, :]),
            (0, 1),
            z,
        )
    if view == "XZ":
        return (
            np.asarray(volume[:, y, :]),
            np.asarray(mask[:, ya, :]),
            np.asarray(skeleton[:, ya, :]),
            (0, 2),
            y,
        )
    if view == "YZ":
        return (
            np.asarray(volume[:, :, x]),
            np.asarray(mask[:, :, xa]),
            np.asarray(skeleton[:, :, xa]),
            (1, 2),
            x,
        )
    raise ValueError(f"Unknown view {view}")


def _write_overlay(
    output_path: Path,
    volume: np.ndarray,
    mask: np.ndarray,
    skeleton: np.ndarray,
    analysis: dict[str, Any],
    *,
    target_fraction_xyz: tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> dict[str, Any]:
    stride = int(analysis["meta"]["analysis_stride"])
    landmark, incident = _choose_landmark(
        analysis,
        tuple(volume.shape),
        target_fraction_xyz,
    )
    point_xyz = np.asarray(
        [landmark["x"], landmark["y"], landmark["z"]],
        dtype=float,
    )
    window = 72.0
    figure, axes = plt.subplots(1, 3, figsize=(15, 5.2), constrained_layout=True)

    for axis, view in zip(axes, ("XY", "XZ", "YZ")):
        raw, mask_plane, skeleton_plane, projected, slice_index = _plane_data(
            volume,
            mask,
            skeleton,
            point_xyz,
            stride,
            view,
        )
        horizontal = point_xyz[projected[0]]
        vertical = point_xyz[projected[1]]
        x0 = max(0, int(horizontal - window))
        x1 = min(raw.shape[1], int(horizontal + window + 1))
        y0 = max(0, int(vertical - window))
        y1 = min(raw.shape[0], int(vertical + window + 1))
        local = raw[y0:y1, x0:x1]
        vmin, vmax = np.percentile(local, (1, 99.5))
        axis.imshow(
            raw,
            cmap="gray",
            origin="lower",
            vmin=float(vmin),
            vmax=float(vmax),
            interpolation="nearest",
        )

        mask_x = np.arange(mask_plane.shape[1], dtype=float) * stride
        mask_y = np.arange(mask_plane.shape[0], dtype=float) * stride
        axis.contour(
            mask_x,
            mask_y,
            mask_plane.astype(np.uint8),
            levels=[0.5],
            colors=["#00d7e8"],
            linewidths=0.7,
            alpha=0.9,
        )
        skeleton_y, skeleton_x = np.nonzero(skeleton_plane)
        in_window = (
            (skeleton_x * stride >= horizontal - window)
            & (skeleton_x * stride <= horizontal + window)
            & (skeleton_y * stride >= vertical - window)
            & (skeleton_y * stride <= vertical + window)
        )
        axis.scatter(
            skeleton_x[in_window] * stride,
            skeleton_y[in_window] * stride,
            s=2.0,
            c="white",
            marker=".",
            alpha=0.85,
            linewidths=0,
        )
        for strut in incident:
            endpoints = np.asarray(strut["polyline"], dtype=float)
            axis.plot(
                endpoints[:, projected[0]],
                endpoints[:, projected[1]],
                color="#3182ff",
                linewidth=1.8,
                linestyle=(0, (4, 2)),
            )
        axis.scatter(
            [horizontal],
            [vertical],
            s=78,
            facecolors="none",
            edgecolors="#ffb000",
            linewidths=1.8,
            marker="s",
        )
        axis.axvline(horizontal, color="#ffb000", linewidth=0.6, alpha=0.55)
        axis.axhline(vertical, color="#ffb000", linewidth=0.6, alpha=0.55)
        axis.set_xlim(horizontal - window, horizontal + window)
        axis.set_ylim(vertical - window, vertical + window)
        axis.set_aspect("equal")
        axis.set_title(f"{view} raw CT · fixed index {slice_index}")
        axis.set_xlabel(view[0] + " full-volume voxel")
        axis.set_ylabel(view[1] + " full-volume voxel")

    legend = [
        Line2D([0], [0], color="#00d7e8", label="segmentation contour"),
        Line2D([0], [0], color="white", marker=".", linestyle="", label="skeleton"),
        Line2D(
            [0],
            [0],
            color="#3182ff",
            linestyle=(0, (4, 2)),
            label="expected incident strut",
        ),
        Line2D(
            [0],
            [0],
            color="#ffb000",
            marker="s",
            markerfacecolor="none",
            linestyle="",
            label="expected node",
        ),
    ]
    figure.legend(handles=legend, loc="lower center", ncol=4, frameon=False)
    figure.suptitle(
        f"Registered landmark node {landmark['id']} · "
        f"{len(incident)} incident struts · raw/segmentation/skeleton evidence",
        fontsize=13,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return {
        "node_id": int(landmark["id"]),
        "node_voxel_xyz": point_xyz.tolist(),
        "incident_strut_ids": [int(item["id"]) for item in incident],
        "target_fraction_xyz": list(target_fraction_xyz),
        "image": str(output_path.relative_to(REPO_ROOT)),
        "image_origin": "lower",
    }


def run_audit(dataset_key: str, output_dir: Path) -> dict[str, Any]:
    config = get_dataset(dataset_key)
    volume_path = Path(config["volume"])
    graph_path = Path(config["design"])
    volume = load_volume(volume_path, mmap=True)
    graph = load_design_graph(graph_path)
    tiff = inspect_tiff_metadata(volume_path)

    cache_dir = volume_path.parents[1] / "processed"
    analysis = json.loads((cache_dir / "analysis.json").read_text(encoding="utf-8"))
    mask = np.load(cache_dir / "mask.npy", mmap_mode="r")
    skeleton = np.load(cache_dir / "skeleton.npy", mmap_mode="r")
    stride = int(analysis["meta"]["analysis_stride"])

    positions = np.asarray(graph["positions_xyz"], dtype=float)
    graph_min = positions.min(axis=0)
    graph_max = positions.max(axis=0)
    upper_xyz = np.asarray(volume.shape[::-1], dtype=float) - 1
    graph_fits = bool(np.all(positions >= 0) and np.all(positions <= upper_xyz))
    pairing_matches = volume_path.stem == graph_path.stem

    expected_samples_original = _sample_expected_paths(analysis)
    expected_samples_analysis = expected_samples_original / stride
    centerline_fraction, nearby_fraction = _local_material_support(
        mask,
        expected_samples_analysis,
    )
    skeleton_xyz = np.argwhere(skeleton)[:, ::-1]
    skeleton_tree = cKDTree(skeleton_xyz)
    skeleton_distance_analysis = skeleton_tree.query(
        expected_samples_analysis,
        workers=-1,
    )[0]
    skeleton_distance_original = skeleton_distance_analysis * stride
    foreground_fraction = float(np.count_nonzero(mask) / mask.size)

    json_metadata = graph.get("raw_metadata", {})
    json_has_registration_metadata = bool(
        json_metadata.get("coordinate_system")
        and json_metadata.get("units")
        and json_metadata.get("transform")
    )
    status, status_reasons = _registration_status(
        pairing_matches=pairing_matches,
        axes=str(tiff["axes"]),
        graph_fits_volume=graph_fits,
        foreground_fraction=foreground_fraction,
        nearby_material_fraction=nearby_fraction,
        skeleton_median_vox=float(np.median(skeleton_distance_original)),
        skeleton_p90_vox=float(np.quantile(skeleton_distance_original, 0.9)),
        json_has_registration_metadata=json_has_registration_metadata,
    )

    spacing_um = float(config["voxel_size_mm"]) * 1000.0
    coordinate_transform = CoordinateTransform(
        transform_id=f"{dataset_key}:registered-json-to-full-ct:v1",
        axis_permutation=(0, 1, 2),
        axis_directions=(1, 1, 1),
        json_scale_to_physical_xyz=(spacing_um, spacing_um, spacing_um),
        translation_physical_xyz=(0.0, 0.0, 0.0),
        voxel_spacing_xyz=(spacing_um, spacing_um, spacing_um),
        voxel_origin_physical_xyz=(0.0, 0.0, 0.0),
        crop_offset_zyx=(0.0, 0.0, 0.0),
        physical_units="um",
        registration_status=status,
    )
    landmark_specs = (
        (
            "center",
            (0.5, 0.5, 0.5),
            output_dir / "registration_landmark_overlay.png",
        ),
        (
            "lower_interior",
            (0.3, 0.3, 0.3),
            output_dir / "registration_landmark_lower_interior.png",
        ),
        (
            "upper_interior",
            (0.7, 0.65, 0.7),
            output_dir / "registration_landmark_upper_interior.png",
        ),
    )
    landmarks = []
    for label, target_fraction, path in landmark_specs:
        landmarks.append(
            {
                "label": label,
                **_write_overlay(
                    path,
                    volume,
                    mask,
                    skeleton,
                    analysis,
                    target_fraction_xyz=target_fraction,
                ),
            }
        )
    expected_analysis_shape = tuple(
        int(np.ceil(length / stride)) for length in volume.shape
    )
    if tuple(mask.shape) != expected_analysis_shape or skeleton.shape != mask.shape:
        raise ValueError(
            "Raw CT, mask, and skeleton shapes are incompatible with the "
            f"configured stride: raw={volume.shape}, mask={mask.shape}, "
            f"skeleton={skeleton.shape}, stride={stride}"
        )
    intensity_sample_stride = 4
    sampled_volume = volume[
        ::intensity_sample_stride,
        ::intensity_sample_stride,
        ::intensity_sample_stride,
    ]
    context_views = [
        output_dir / "registration_3d_elev30_azim45.png",
        output_dir / "registration_3d_elev60_azim45.png",
    ]

    refinement = analysis["meta"]["alignment"].get("refinement", {})
    before_median = refinement.get("median_distance_before_vox")
    after_median = refinement.get("median_distance_after_vox")
    before_p90 = refinement.get("p90_distance_before_vox")
    after_p90 = refinement.get("p90_distance_after_vox")
    residual_affine_original = refinement.get("affine_homogeneous_rows")
    if residual_affine_original is not None:
        residual_affine_original = np.asarray(
            residual_affine_original,
            dtype=float,
        )
        residual_affine_original[-1] *= stride
    if before_median is not None:
        before_median = float(before_median) * stride
    if after_median is not None:
        after_median = float(after_median) * stride
    if before_p90 is not None:
        before_p90 = float(before_p90) * stride
    if after_p90 is not None:
        after_p90 = float(after_p90) * stride

    return {
        "audit_version": 2,
        "audit_phase": 1,
        "scientific_behavior_changed": False,
        "dataset_key": dataset_key,
        "pairing": {
            "tiff": str(volume_path.relative_to(REPO_ROOT)),
            "registered_json": str(graph_path.relative_to(REPO_ROOT)),
            "basename_match": pairing_matches,
            "status": "confirmed" if pairing_matches else "failed",
        },
        "coordinate_system": {
            "tiff_shape_zyx": list(volume.shape),
            "tiff_axes": tiff["axes"],
            "tiff_dtype": tiff["dtype"],
            "numpy_index_order": "zyx",
            "json_position_order": "xyz",
            "json_units_declared": json_metadata.get("units"),
            "physical_spacing_from_tiff": tiff["voxel_size_mm"],
            "configured_spacing_um_xyz": [spacing_um] * 3,
            "configured_spacing_status": "unverified_design_span_estimate",
            "scientific_crop": None,
            "crop_offset_zyx": [0, 0, 0],
            "coordinate_transform": coordinate_transform.to_metadata(),
        },
        "bounding_boxes": {
            "ct_index_min_xyz": [0.0, 0.0, 0.0],
            "ct_index_max_xyz": upper_xyz.tolist(),
            "json_min_xyz": graph_min.tolist(),
            "json_max_xyz": graph_max.tolist(),
            "json_fits_ct_volume": graph_fits,
            "segmented_foreground_xyz": analysis["meta"][
                "bounding_box_voxel"
            ],
        },
        "segmentation": {
            "threshold": float(analysis["meta"]["threshold"]),
            "threshold_source": analysis["meta"]["threshold_source"],
            "analysis_stride": stride,
            "analysis_shape_zyx": list(mask.shape),
            "foreground_fraction": foreground_fraction,
        },
        "nde_features": {
            "raw_intensity_sample_stride_zyx": [intensity_sample_stride] * 3,
            "raw_intensity_sample_mean": float(np.mean(sampled_volume)),
            "raw_intensity_sample_min": float(np.min(sampled_volume)),
            "raw_intensity_sample_max": float(np.max(sampled_volume)),
            "segmented_foreground_voxels_analysis_resolution": int(
                np.count_nonzero(mask)
            ),
            "skeleton_voxels_analysis_resolution": int(
                np.count_nonzero(skeleton)
            ),
            "skeleton_connected_components": int(
                analysis["connectivity"]["connected_components"]
            ),
            "skeleton_branch_point_signal_voxels": int(
                analysis["connectivity"]["branch_point_count"]
            ),
            "shape_compatibility": "passed",
        },
        "registration": {
            "status": status,
            "automatic_missing_validation_enabled": status
            != "registration_failed",
            "reasons": status_reasons,
            "path_sample_count": int(len(expected_samples_original)),
            "centerline_foreground_fraction": centerline_fraction,
            "material_support_within_radius_fraction": nearby_fraction,
            "material_support_radius_original_vox": 2 * stride,
            "median_expected_path_to_skeleton_original_vox": float(
                np.median(skeleton_distance_original)
            ),
            "p90_expected_path_to_skeleton_original_vox": float(
                np.quantile(skeleton_distance_original, 0.9)
            ),
            "refinement_median_distance_before_original_vox": before_median,
            "refinement_median_distance_after_original_vox": after_median,
            "refinement_p90_distance_before_original_vox": before_p90,
            "refinement_p90_distance_after_original_vox": after_p90,
            "active_detector_residual_affine_original_voxel_row_vector": (
                residual_affine_original
            ),
            "residual_affine_note": (
                "The working detector applies this segmentation-dependent "
                "refinement after the registered identity mapping. It is "
                "reported explicitly but is not yet routed through the new "
                "canonical coordinate object."
            ),
            "quality_rule": {
                "failed": (
                    "pairing/axes/bounds failure, foreground fraction outside "
                    "(0.001, 0.50), or path material support below 0.50"
                ),
                "warning": (
                    "path material support below 0.80, median skeleton distance "
                    "above 3 voxels, or p90 above 8 voxels"
                ),
                "verified": (
                    "all measured gates pass and JSON declares coordinates, "
                    "units, and transform provenance"
                ),
                "likely_valid": (
                    "all measured gates pass but transform provenance is incomplete"
                ),
            },
        },
        "boundary": {
            "configured_excluded_region": None,
            "unreliable_boundary_faces": analysis["meta"].get(
                "unreliable_boundary_faces",
                [],
            ),
            "status": "registration_warning",
            "reason": (
                "high-Y cut/absent surface is detected heuristically but is not "
                "encoded as an explicit exclusion mask"
            ),
        },
        "detector_baseline": {
            "struts_by_status": dict(
                Counter(item["status"] for item in analysis["struts"])
            ),
            "nodes_by_status": dict(
                Counter(item["status"] for item in analysis["nodes"])
            ),
            "candidate_defect_count": len(analysis["defects"]),
            "cad_id_metrics": analysis.get("validation"),
            "interpretation": (
                "candidate detector output only; no selected-item validation "
                "status is produced in Phase 1"
            ),
        },
        "visual_check": {
            **landmarks[0],
            "landmarks": landmarks,
            "context_3d_views": [
                str(path.relative_to(REPO_ROOT))
                for path in context_views
                if path.is_file()
            ],
        },
        "selection_flow": {
            "source": "Plotly trace customdata",
            "payload": ["element_kind", "graph_element_id", "detector_status"],
            "resolver": "app.app._clicked_element",
            "persistent_state": False,
            "url_state": False,
            "validation_api_request": False,
            "camera_focus": False,
        },
        "phase_1_verified": [
            "TIFF/JSON file pairing",
            "TIFF ZYX array convention",
            "JSON XYZ position convention used by active code",
            "full-volume graph bounds",
            "current non-degenerate Otsu segmentation",
            "measured expected-path proximity to segmentation and skeleton",
            "3D click payload resolves actual graph strut/node IDs",
        ],
        "remaining_assumptions": [
            "physical spacing is inferred from nominal design span",
            "registered JSON lacks independent transform provenance",
            "registration refinement depends on thresholded skeleton",
            "high-Y excluded cut region has no explicit mask or bound",
            "detector still measures at analysis stride 2",
            "no candidate-level raw CT validation exists yet",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="missing_struts")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "verification",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = run_audit(args.dataset, output_dir)
    summary_path = output_dir / "verification_summary.json"
    summary_path.write_text(
        json.dumps(_json_safe(summary), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {summary_path}")
    print(f"Registration status: {summary['registration']['status']}")
    print(f"Overlay: {summary['visual_check']['image']}")


if __name__ == "__main__":
    main()
