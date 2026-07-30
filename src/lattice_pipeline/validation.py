"""CAD-grounded validation and boundary-quality checks for defect results."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree


_BINARY_STL_TRIANGLE = np.dtype(
    [
        ("normal", "<f4", (3,)),
        ("vertices", "<f4", (3, 3)),
        ("attribute", "<u2"),
    ]
)

CONTINUITY_DEFECT_STATUSES = frozenset({"missing", "disconnected"})


def _point_key(point: Sequence[float]) -> tuple[float, float, float]:
    return tuple(float(value) for value in np.round(point, 8))


def _edge_key(
    start: Sequence[float],
    end: Sequence[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return tuple(sorted((_point_key(start), _point_key(end))))  # type: ignore[return-value]


def _stl_centroid_distances(path: str | Path, points: np.ndarray) -> np.ndarray:
    """Return nearest surface-triangle-centroid distances for a binary STL."""

    stl_path = Path(path)
    size = stl_path.stat().st_size
    if size < 84 or (size - 84) % _BINARY_STL_TRIANGLE.itemsize:
        raise ValueError(f"Expected a binary STL with 50-byte triangles: {stl_path}")
    triangles = np.memmap(
        stl_path,
        dtype=_BINARY_STL_TRIANGLE,
        mode="r",
        offset=84,
    )
    centroids = np.asarray(triangles["vertices"]).mean(axis=1, dtype=np.float32)
    tree = cKDTree(centroids, compact_nodes=False, balanced_tree=False)
    return np.asarray(tree.query(points, workers=-1)[0], dtype=float)


@lru_cache(maxsize=4)
def intentional_missing_strut_ids(
    nominal_graph_path: str,
    baseline_stl_path: str,
    defect_stl_path: str,
    physical_span_mm: float,
    symmetry_values: tuple[float, ...],
    *,
    baseline_surface_cutoff_mm: float = 0.30,
    missing_surface_distance_mm: float = 0.50,
) -> tuple[int, ...]:
    """Derive intentional removals by comparing complete and defect CAD STLs.

    The baseline graph supplies stable element IDs. A strut is intentional
    ground truth only when its midpoint is close to the complete STL and
    cleanly absent from the defect STL. The configured proper cube symmetry
    maps CAD orientation onto the registered graph orientation.
    """

    raw = json.loads(Path(nominal_graph_path).read_text(encoding="utf-8"))
    nodes = raw["junctions"]
    struts = raw["struts"]
    positions = {
        int(node["id"]): np.asarray(node["position"], dtype=float)
        for node in nodes
    }
    all_positions = np.asarray(list(positions.values()))
    minimum = all_positions.min(axis=0)
    maximum = all_positions.max(axis=0)
    span = maximum - minimum
    if np.any(span <= 0):
        raise ValueError("Nominal graph has a degenerate coordinate span")
    center = (minimum + maximum) / 2
    scale = float(physical_span_mm) / span
    midpoints = np.asarray(
        [
            (positions[int(strut["junction0"])] + positions[int(strut["junction1"])])
            / 2
            for strut in struts
        ]
    )
    query_mm = (midpoints - center) * scale
    baseline_distance = _stl_centroid_distances(baseline_stl_path, query_mm)
    defect_distance = _stl_centroid_distances(defect_stl_path, query_mm)
    removed_indices = np.flatnonzero(
        (baseline_distance <= baseline_surface_cutoff_mm)
        & (defect_distance > missing_surface_distance_mm)
    )

    symmetry = np.asarray(symmetry_values, dtype=float)
    if symmetry.shape != (9,):
        raise ValueError("CAD-to-graph symmetry must contain nine matrix values")
    symmetry = symmetry.reshape(3, 3)
    if not np.isclose(abs(np.linalg.det(symmetry)), 1):
        raise ValueError("CAD-to-graph symmetry must be an orthogonal cube symmetry")

    edge_lookup = {
        _edge_key(
            positions[int(strut["junction0"])],
            positions[int(strut["junction1"])],
        ): int(strut["id"])
        for strut in struts
    }
    mapped_ids: list[int] = []
    for index in removed_indices:
        strut = struts[int(index)]
        start = (
            positions[int(strut["junction0"])] - center
        ) @ symmetry + center
        end = (
            positions[int(strut["junction1"])] - center
        ) @ symmetry + center
        key = _edge_key(start, end)
        if key not in edge_lookup:
            raise ValueError("CAD symmetry produced a strut absent from the nominal graph")
        mapped_ids.append(edge_lookup[key])
    return tuple(sorted(mapped_ids))


def mark_unreliable_boundary_faces(
    result: dict[str, Any],
    nominal_graph: Mapping[str, Any],
    *,
    missing_present_fraction: float,
    unreliable_missing_rate: float = 0.50,
) -> list[dict[str, Any]]:
    """Downgrade scan-wide missing boundary planes to ``uncertain``.

    A genuine random-removal design cannot plausibly remove most of a complete
    exterior face. Such a plane is evidence of cropping or registration error.
    """

    nominal_nodes = {
        int(node["id"]): np.asarray(node["position"], dtype=float)
        for node in nominal_graph["junctions"]
    }
    positions = np.asarray(list(nominal_nodes.values()))
    bounds = (positions.min(axis=0), positions.max(axis=0))
    result_struts = {int(item["id"]): item for item in result["struts"]}
    unreliable: list[dict[str, Any]] = []
    unreliable_strut_ids: set[int] = set()
    unreliable_node_ids: set[int] = set()

    for axis, axis_name in enumerate(("X", "Y", "Z")):
        for side, boundary in (("low", bounds[0][axis]), ("high", bounds[1][axis])):
            face_struts = []
            face_nodes: set[int] = set()
            for source in nominal_graph["struts"]:
                node_a = int(source["junction0"])
                node_b = int(source["junction1"])
                if np.isclose(nominal_nodes[node_a][axis], boundary) and np.isclose(
                    nominal_nodes[node_b][axis],
                    boundary,
                ):
                    strut_id = int(source["id"])
                    if strut_id in result_struts:
                        face_struts.append(result_struts[strut_id])
                        face_nodes.update((node_a, node_b))
            if not face_struts:
                continue
            missing_rate = float(
                np.mean(
                    [
                        float(item.get("present_fraction", 1.0))
                        < missing_present_fraction
                        for item in face_struts
                    ]
                )
            )
            if missing_rate < unreliable_missing_rate:
                continue
            unreliable.append(
                {
                    "axis": axis_name,
                    "side": side,
                    "strut_count": len(face_struts),
                    "missing_evidence_fraction": missing_rate,
                    "reason": "scan_boundary_or_registration_mismatch",
                }
            )
            unreliable_strut_ids.update(int(item["id"]) for item in face_struts)
            unreliable_node_ids.update(face_nodes)

    for item in result["struts"]:
        if int(item["id"]) in unreliable_strut_ids and item["status"] == "missing":
            item["status"] = "uncertain"
            item["rule_strength"] = 0.5
            item.pop("confidence", None)
            item["boundary_reason"] = "unreliable_design_face"
    for item in result["nodes"]:
        if int(item["id"]) in unreliable_node_ids and item["status"] == "missing":
            item["status"] = "uncertain"
            item["rule_strength"] = 0.5
            item.pop("confidence", None)
            item["boundary_reason"] = "unreliable_design_face"

    element_status = {
        ("strut", int(item["id"])): item["status"] for item in result["struts"]
    }
    element_status.update(
        {("node", int(item["id"])): item["status"] for item in result["nodes"]}
    )
    for defect in result["defects"]:
        affected = defect.get("affected_element", {})
        key = (affected.get("kind"), int(affected.get("id", -1)))
        status = element_status.get(key)
        if status is None:
            continue
        defect["type"] = status
        if status == "uncertain":
            defect["severity"] = "low"
            defect["rule_strength"] = 0.5
            defect.pop("confidence", None)
            defect.setdefault("evidence", {})[
                "boundary_reason"
            ] = "unreliable_design_face"
    return unreliable


def evaluate_against_intentional_missing(
    result: Mapping[str, Any],
    nominal_graph: Mapping[str, Any],
    expected_strut_ids: Sequence[int],
) -> dict[str, Any]:
    """Return ID-level missing/disconnected detection metrics against CAD removals.

    The defect CAD supplies intentional-removal ground truth. Both ``missing`` and
    ``disconnected`` detector labels are positive predictions so continuity
    failures participate in the confusion matrix.
    """

    expected_struts = {int(value) for value in expected_strut_ids}
    predicted_struts = {
        int(item["id"])
        for item in result["struts"]
        if item["status"] in CONTINUITY_DEFECT_STATUSES
    }
    incident: dict[int, set[int]] = defaultdict(set)
    for strut in nominal_graph["struts"]:
        strut_id = int(strut["id"])
        incident[int(strut["junction0"])].add(strut_id)
        incident[int(strut["junction1"])].add(strut_id)
    expected_nodes = {
        node_id
        for node_id, strut_ids in incident.items()
        if strut_ids and strut_ids <= expected_struts
    }
    predicted_nodes = {
        int(item["id"])
        for item in result["nodes"]
        if item["status"] in CONTINUITY_DEFECT_STATUSES
    }

    strut_universe = {
        int(item["id"]) for item in nominal_graph["struts"]
    } | {int(item["id"]) for item in result["struts"]}
    node_universe = {
        int(item["id"]) for item in nominal_graph["junctions"]
    } | {int(item["id"]) for item in result["nodes"]}

    def metrics(
        expected: set[int],
        predicted: set[int],
        universe: set[int],
    ) -> dict[str, Any]:
        true_positive = expected & predicted
        false_positive = predicted - expected
        false_negative = expected - predicted
        true_negative = universe - (expected | predicted)
        confusion_total = (
            len(true_positive)
            + len(true_negative)
            + len(false_positive)
            + len(false_negative)
        )
        precision = len(true_positive) / len(predicted) if predicted else 0.0
        recall = len(true_positive) / len(expected) if expected else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        accuracy = (
            (len(true_positive) + len(true_negative)) / confusion_total
            if confusion_total
            else 0.0
        )
        return {
            "total": len(universe),
            "expected": len(expected),
            "predicted": len(predicted),
            "true_positive": len(true_positive),
            "true_negative": len(true_negative),
            "false_positive": len(false_positive),
            "false_negative": len(false_negative),
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positive_ids": sorted(true_positive),
            "false_positive_ids": sorted(false_positive),
            "false_negative_ids": sorted(false_negative),
        }

    strut_metrics = metrics(expected_struts, predicted_struts, strut_universe)
    node_metrics = metrics(expected_nodes, predicted_nodes, node_universe)
    overall_counts = {
        name: int(strut_metrics[name]) + int(node_metrics[name])
        for name in (
            "total",
            "expected",
            "predicted",
            "true_positive",
            "true_negative",
            "false_positive",
            "false_negative",
        )
    }
    overall_precision = (
        overall_counts["true_positive"]
        / (overall_counts["true_positive"] + overall_counts["false_positive"])
        if overall_counts["true_positive"] + overall_counts["false_positive"]
        else 0.0
    )
    overall_recall = (
        overall_counts["true_positive"]
        / (overall_counts["true_positive"] + overall_counts["false_negative"])
        if overall_counts["true_positive"] + overall_counts["false_negative"]
        else 0.0
    )
    overall_confusion_total = sum(
        overall_counts[name]
        for name in (
            "true_positive",
            "true_negative",
            "false_positive",
            "false_negative",
        )
    )
    overall = {
        **overall_counts,
        "accuracy": (
            (overall_counts["true_positive"] + overall_counts["true_negative"])
            / overall_confusion_total
            if overall_confusion_total
            else 0.0
        ),
        "precision": overall_precision,
        "recall": overall_recall,
        "f1": (
            2
            * overall_precision
            * overall_recall
            / (overall_precision + overall_recall)
            if overall_precision + overall_recall
            else 0.0
        ),
    }

    return {
        "method": "complete_vs_defect_cad_midpoint_surface_distance",
        "scope": "binary_missing_or_disconnected_detection_against_cad_removals",
        "positive_statuses": sorted(CONTINUITY_DEFECT_STATUSES),
        "ground_truth_status": "intentional_missing",
        "ground_truth_note": (
            "The paired CAD models identify intentional removals. Disconnected "
            "predictions are included, but no independent disconnected-element "
            "ground-truth IDs are available."
        ),
        "overall": overall,
        "struts": strut_metrics,
        "nodes": node_metrics,
        "expected_strut_ids": sorted(expected_struts),
        "expected_missing_node_ids": sorted(expected_nodes),
    }


__all__ = [
    "evaluate_against_intentional_missing",
    "intentional_missing_strut_ids",
    "mark_unreliable_boundary_faces",
]
