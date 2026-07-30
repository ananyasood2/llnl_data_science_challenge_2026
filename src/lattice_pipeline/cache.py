"""Cache-first orchestration for the lattice inspection dashboard."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

from .align import (
    mask_bbox_xyz,
    refine_positions_to_skeleton,
    resolve_alignment,
)
from .defects import DefectConfig, classify_defects
from .io import inspect_tiff_metadata, load_design_graph, load_volume
from .segment import otsu_threshold, segment_with_metadata
from .skeleton import analyze_skeleton, skeletonize_mask
from .validation import (
    evaluate_against_intentional_missing,
    intentional_missing_strut_ids,
    mark_unreliable_boundary_faces,
)

ANALYSIS_VERSION = 9


def _source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _cache_dir(config: dict[str, Any]) -> Path:
    path = Path(config["volume"])
    if "tif_stacks" in path.parts:
        root = path.parents[1]
    else:
        root = path.parent
    return root / "processed"


def _sampled_otsu(volume: np.ndarray, target_voxels: int = 10_000_000) -> float:
    stride = max(1, int(np.ceil((volume.size / target_voxels) ** (1 / 3))))
    return otsu_threshold(volume[::stride, ::stride, ::stride])


def _aligned_graph(
    graph: dict[str, Any],
    transform: Any,
    analysis_stride: int,
    *,
    positions_analysis_xyz: np.ndarray | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positions = (
        np.asarray(positions_analysis_xyz, dtype=float)
        if positions_analysis_xyz is not None
        else transform.apply(graph["positions_xyz"]) / analysis_stride
    )
    nodes: list[dict[str, Any]] = []
    for source, position in zip(graph["junctions"], positions):
        nodes.append(
            {
                "id": int(source["id"]),
                "design_node_id": int(source["id"]),
                "position": position.tolist(),
                "indices": source.get("indices"),
            }
        )
    struts = [
        {
            **source,
            "id": int(source["id"]),
            "node_a": int(source["junction0"]),
            "node_b": int(source["junction1"]),
        }
        for source in graph["struts"]
    ]
    return nodes, struts


def _restore_original_voxels(result: dict[str, Any], stride: int) -> None:
    if stride == 1:
        return
    for node in result["nodes"]:
        for axis in ("x", "y", "z"):
            node[axis] = float(node[axis] * stride)
        if "position" in node:
            node["position"] = [float(v * stride) for v in node["position"]]
    for strut in result["struts"]:
        strut["polyline"] = [
            [float(v * stride) for v in point] for point in strut["polyline"]
        ]
    for defect in result["defects"]:
        defect["location_voxel"] = [
            float(v * stride) for v in defect["location_voxel"]
        ]
        defect["slice_index"] = int(round(defect["slice_index"] * stride))
        metric = defect.get("size_metric")
        if metric and metric.get("unit") == "voxel":
            metric["value"] = round(float(metric["value"] * stride), 3)


def ensure_analysis(
    dataset_key: str,
    config: dict[str, Any],
    *,
    threshold: float | None = None,
    voxel_size_mm: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build or load cached mask/skeleton/EDT and the shared analysis JSON."""

    volume_path = Path(config["volume"])
    design_path = Path(config["design"])
    cache_dir = _cache_dir(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    mask_path = cache_dir / "mask.npy"
    skeleton_path = cache_dir / "skeleton.npy"
    distance_path = cache_dir / "distance_map.npy"
    analysis_path = cache_dir / "analysis.json"
    cache_meta_path = cache_dir / "cache_meta.json"

    stride = int(config.get("analysis_stride", 1))
    voxel_size = float(voxel_size_mm or config["voxel_size_mm"])
    signature = {
        "volume": _source_signature(volume_path),
        "design": _source_signature(design_path),
        "threshold_request": threshold,
        "analysis_stride": stride,
        "pipeline_version": 4,
    }
    fingerprint = hashlib.sha256(
        json.dumps(signature, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cached_meta = {}
    if cache_meta_path.is_file():
        try:
            cached_meta = json.loads(cache_meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cached_meta = {}
    arrays_valid = (
        not force
        and cached_meta.get("fingerprint") == fingerprint
        and all(path.is_file() for path in (mask_path, skeleton_path, distance_path))
    )

    volume = load_volume(volume_path, mmap=True)
    if arrays_valid:
        mask = np.load(mask_path, mmap_mode="r")
        skeleton = np.load(skeleton_path, mmap_mode="r")
        distance_map = np.load(distance_path, mmap_mode="r")
        segmentation_meta = cached_meta["segmentation"]
    else:
        used_threshold = _sampled_otsu(volume) if threshold is None else float(threshold)
        analysis_volume = volume[::stride, ::stride, ::stride]
        mask, segmentation_meta = segment_with_metadata(
            analysis_volume, threshold=used_threshold
        )
        segmentation_meta["threshold_source"] = (
            "sampled_otsu" if threshold is None else "user_override"
        )
        segmentation_meta["analysis_stride"] = stride
        np.save(mask_path, mask)

        # These are the two most expensive threshold-dependent volume
        # operations, and neither depends on the other's result.  Both
        # scikit-image and SciPy release the GIL while doing their numeric
        # work, so overlapping them materially reduces an interactive
        # threshold rebuild without changing either result.
        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="lattice-volume",
        ) as executor:
            skeleton_future = executor.submit(skeletonize_mask, mask)
            distance_future = executor.submit(ndimage.distance_transform_edt, mask)
            skeleton = skeleton_future.result()
            distance_map = distance_future.result().astype(np.float32)
        np.save(skeleton_path, skeleton)
        np.save(distance_path, distance_map)
        cached_meta = {
            "fingerprint": fingerprint,
            "signature": signature,
            "segmentation": segmentation_meta,
        }
        _atomic_json(cache_meta_path, cached_meta)

    if (
        not force
        and arrays_valid
        and analysis_path.is_file()
    ):
        try:
            cached_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            if (
                cached_analysis["meta"].get("analysis_version") == ANALYSIS_VERSION
                and abs(float(cached_analysis["meta"]["voxel_size_mm"]) - voxel_size) < 1e-12
            ):
                cached_analysis["_cache"] = {
                    "hit": True,
                    "directory": str(cache_dir),
                }
                return cached_analysis
        except (KeyError, ValueError, json.JSONDecodeError, OSError):
            pass

    graph = load_design_graph(design_path)
    bbox_analysis = mask_bbox_xyz(np.asarray(mask))
    bbox_original = {
        key: [float(v * stride) for v in values]
        for key, values in bbox_analysis.items()
    }
    registered = config.get("alignment_source") == "registered_json"
    transform = resolve_alignment(
        graph,
        volume_shape_zyx=volume.shape,
        scan_bbox_xyz=bbox_original,
        registered=registered,
    )
    aligned_positions = transform.apply(graph["positions_xyz"]) / stride
    refinement_meta: dict[str, Any] = {
        "applied": False,
        "reason": "not_a_registered_design",
    }
    if registered:
        node_row = {
            int(node["id"]): index
            for index, node in enumerate(graph["junctions"])
        }
        edge_indices = np.asarray(
            [
                [
                    node_row[int(strut["junction0"])],
                    node_row[int(strut["junction1"])],
                ]
                for strut in graph["struts"]
            ],
            dtype=np.int64,
        )
        aligned_positions, refinement_meta = refine_positions_to_skeleton(
            aligned_positions,
            edge_indices,
            skeleton,
        )
    design_nodes, design_struts = _aligned_graph(
        graph,
        transform,
        stride,
        positions_analysis_xyz=aligned_positions,
    )
    missing_fraction = 0.15 if dataset_key == "missing_struts" else 0.22
    defect_result = classify_defects(
        mask,
        skeleton,
        distance_map,
        design_nodes,
        design_struts,
        voxel_size * stride,
        config=DefectConfig(
            presence_radius_vox=(
                2.25
                if dataset_key == "missing_struts"
                else max(2.5, 5.0 / stride)
            ),
            node_presence_radius_vox=(
                15.0 if dataset_key == "unitcell" else 6.0
            ),
            missing_present_fraction=missing_fraction,
            endpoint_to_strut_radius_vox=max(3.5, 7.0 / stride),
            endpoint_to_node_radius_vox=max(3.5, 7.0 / stride),
            crop_margin_vox=max(3.0, 5.0 / stride),
            thin_ratio=0.70 if dataset_key == "unitcell" else 0.80,
            thick_ratio=1.35 if dataset_key == "unitcell" else 1.25,
            thickness_uncertain_band=0.015,
            edt_radius_correction_vox=0.5 / stride,
            nominal_thickness_um=350.0,
        ),
    )
    nominal_graph = None
    unreliable_faces: list[dict[str, Any]] = []
    validation = None
    if config.get("nominal_design"):
        nominal_graph = load_design_graph(Path(config["nominal_design"]))
        unreliable_faces = mark_unreliable_boundary_faces(
            defect_result,
            nominal_graph,
            missing_present_fraction=missing_fraction,
        )
        if all(
            config.get(name)
            for name in (
                "baseline_stl",
                "defect_stl",
                "cad_to_graph_symmetry",
                "cad_physical_span_mm",
            )
        ):
            expected_strut_ids = intentional_missing_strut_ids(
                str(Path(config["nominal_design"]).resolve()),
                str(Path(config["baseline_stl"]).resolve()),
                str(Path(config["defect_stl"]).resolve()),
                float(config["cad_physical_span_mm"]),
                tuple(float(v) for v in config["cad_to_graph_symmetry"]),
            )
            validation = evaluate_against_intentional_missing(
                defect_result,
                nominal_graph,
                expected_strut_ids,
            )
    _restore_original_voxels(defect_result, stride)

    topology = analyze_skeleton(
        skeleton,
        spacing=voxel_size * stride,
        coordinate_limit=2_000,
        include_graph=True,
        max_branches=25_000,
        max_polyline_points=64,
    )
    skeleton_branches = []
    for branch in topology.get("graph", {}).get("branches", []):
        polyline_xyz = [
            [float(value * stride) for value in point[::-1]]
            for point in branch.get("polyline_zyx", [])
        ]
        skeleton_branches.append(
            {
                "id": branch["id"],
                "node_a": branch.get("node_a"),
                "node_b": branch.get("node_b"),
                "length_mm": branch.get("length"),
                "polyline": polyline_xyz,
            }
        )
    foreground_voxels = int(segmentation_meta["foreground_voxels"] * stride**3)
    min_xyz = np.asarray(bbox_original["min_xyz"])
    max_xyz = np.asarray(bbox_original["max_xyz"])
    dimensions_vox = max_xyz - min_xyz + stride
    tiff_meta = (
        inspect_tiff_metadata(volume_path)
        if volume_path.suffix.lower() in {".tif", ".tiff"}
        else None
    )
    analysis = {
        "meta": {
            "dataset_key": dataset_key,
            "analysis_version": ANALYSIS_VERSION,
            "volume_shape": [int(v) for v in volume.shape],
            "analysis_shape": [int(v) for v in mask.shape],
            "analysis_stride": stride,
            "voxel_size_mm": voxel_size,
            "voxel_size_source": (
                "user_override"
                if voxel_size_mm is not None
                else config["voxel_size_source"]
            ),
            "threshold": float(segmentation_meta["threshold"]),
            "threshold_source": segmentation_meta["threshold_source"],
            "alignment": {
                **transform.to_metadata(),
                "refinement": refinement_meta,
            },
            "unreliable_boundary_faces": unreliable_faces,
            "design_graph": {
                "node_count": len(design_nodes),
                "strut_count": len(design_struts),
                "path": str(design_path),
            },
            "tiff_metadata": tiff_meta,
            "bounding_box_voxel": bbox_original,
            "physical_dimensions_mm": (dimensions_vox * voxel_size).round(4).tolist(),
            "foreground_voxels": foreground_voxels,
            "foreground_volume_mm3": float(foreground_voxels * voxel_size**3),
            "cache_fingerprint": fingerprint,
        },
        "nodes": defect_result["nodes"],
        "struts": defect_result["struts"],
        "components": defect_result["components"],
        "defects": defect_result["defects"],
        "connectivity": {
            **defect_result["summary"],
            "skeleton_voxels": topology["skeleton_voxels"],
            "skan_branch_count": topology.get("graph", {}).get("branch_count"),
        },
        "skeleton_graph": {
            "backend": topology.get("graph", {}).get("backend"),
            "branches": skeleton_branches,
            "truncated": topology.get("graph", {}).get("truncated", False),
        },
        "validation": validation,
    }
    _atomic_json(analysis_path, analysis)
    analysis["_cache"] = {"hit": False, "directory": str(cache_dir)}
    return analysis


def load_cached_arrays(config: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Load processed display arrays after :func:`ensure_analysis`."""
    root = _cache_dir(config)
    return (
        np.load(root / "mask.npy", mmap_mode="r"),
        np.load(root / "skeleton.npy", mmap_mode="r"),
    )


__all__ = ["ensure_analysis", "load_cached_arrays"]
