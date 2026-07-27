"""Offline, validation-first mapping of CAD design intent onto registered strut IDs.

The CAD and CT/registered-graph files in this project use different coordinate
systems.  This module deliberately treats a mapping as unavailable unless its
registration is unambiguous.  That prevents a geometrically plausible but
incorrect lattice-symmetry orientation from being reported as an intentional
defect in the dashboard.

It is intended to be run as an offline preprocessing step.  The API only
loads the small JSON artifact it creates; it never reads or modifies the STL
files during a dashboard request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import permutations, product
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree


ARTIFACT_VERSION = "1.0.0"
STATUS_VALIDATED = "validated"
STATUS_UNAVAILABLE = "unavailable"

# The files are binary STL exports in this data set.  Reading facets with a
# memory map is substantially lighter than converting two 3.5M-face meshes to
# Python objects and lets us compare their geometry reproducibly.
_STL_FACET_DTYPE = np.dtype(
    [
        ("normal", "<f4", (3,)),
        ("vectors", "<f4", (3, 3)),
        ("attributes", "<u2"),
    ]
)


@dataclass(frozen=True)
class GraphGeometry:
    """The nominal graph geometry and its stable strut-ID ordering."""

    strut_ids: np.ndarray
    endpoints: np.ndarray
    topology_by_id: dict[int, tuple[int, int]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _read_graph(path: Path) -> tuple[GraphGeometry, dict[int, np.ndarray]]:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)

    junction_positions = {
        int(junction["id"]): np.asarray(junction["position"], dtype=float)
        for junction in payload["junctions"]
    }
    ordered_struts = sorted(payload["struts"], key=lambda strut: int(strut["id"]))
    strut_ids = np.asarray([int(strut["id"]) for strut in ordered_struts], dtype=int)
    topology_by_id = {
        int(strut["id"]): tuple(sorted((int(strut["junction0"]), int(strut["junction1"]))))
        for strut in ordered_struts
    }
    endpoints = np.asarray(
        [
            [
                junction_positions[int(strut["junction0"])],
                junction_positions[int(strut["junction1"])],
            ]
            for strut in ordered_struts
        ],
        dtype=float,
    )
    return GraphGeometry(strut_ids, endpoints, topology_by_id), junction_positions


def _validate_graph_id_mapping(nominal_graph: Path, registered_graph: Path) -> dict[str, Any]:
    nominal, _ = _read_graph(nominal_graph)
    registered, _ = _read_graph(registered_graph)
    nominal_ids = set(nominal.topology_by_id)
    registered_ids = set(registered.topology_by_id)
    matching_ids = nominal_ids == registered_ids
    matching_topology = matching_ids and all(
        nominal.topology_by_id[strut_id] == registered.topology_by_id[strut_id]
        for strut_id in nominal_ids
    )
    return {
        "matching_ids": matching_ids,
        "matching_topology": matching_topology,
        "nominal_strut_count": len(nominal_ids),
        "registered_strut_count": len(registered_ids),
    }


def _load_mesh_metadata(path: Path) -> dict[str, Any]:
    """Use trimesh for STL validation and durable mesh metadata.

    ``process=False`` keeps the source tessellation intact; the exact facet
    comparison below depends on that property.
    """

    import trimesh

    mesh = trimesh.load_mesh(path, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"{path.name} did not load as a single triangular mesh")
    result = {
        "vertex_count": int(len(mesh.vertices)),
        "face_count": int(len(mesh.faces)),
        "bounds": np.asarray(mesh.bounds, dtype=float).round(8).tolist(),
        "extents": np.asarray(mesh.extents, dtype=float).round(8).tolist(),
        "is_watertight": bool(mesh.is_watertight),
    }
    # Explicitly release the very large STL arrays before doing the facet diff.
    del mesh
    return result


def _open_binary_facets(path: Path) -> np.memmap:
    with path.open("rb") as source:
        source.seek(80)
        count_bytes = source.read(4)
    if len(count_bytes) != 4:
        raise ValueError(f"{path.name} is not a supported binary STL file")
    facet_count = int(np.frombuffer(count_bytes, dtype="<u4")[0])
    expected_size = 84 + facet_count * _STL_FACET_DTYPE.itemsize
    if path.stat().st_size != expected_size:
        raise ValueError(f"{path.name} is not a supported binary STL file")
    return np.memmap(path, mode="r", offset=84, dtype=_STL_FACET_DTYPE, shape=(facet_count,))


def _facet_hashes(facets: np.memmap) -> np.ndarray:
    """Return a stable 64-bit hash for each triangle's exact vertex sequence."""

    vertex_words = facets["vectors"].view("<u4").reshape(len(facets), 9)
    hashes = np.full(len(facets), np.uint64(1469598103934665603), dtype=np.uint64)
    for column in range(vertex_words.shape[1]):
        hashes ^= vertex_words[:, column].astype(np.uint64, copy=False)
        hashes *= np.uint64(1099511628211)
    return hashes


def _difference_facet_centers(reference_stl: Path, design_stl: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Find geometry present in the all-strut reference but absent from CAD.

    The paired exports share almost all of their tessellation.  Facet hashing
    is both faster and more deterministic than repeatedly querying a 3.5M-face
    mesh.  The result still represents sampled CAD-surface proximity, because
    each center is sampled from a surface facet absent in the design STL.
    """

    reference_facets = _open_binary_facets(reference_stl)
    design_facets = _open_binary_facets(design_stl)
    reference_hashes = _facet_hashes(reference_facets)
    design_hashes = _facet_hashes(design_facets)
    missing_mask = ~np.isin(reference_hashes, design_hashes, assume_unique=False)
    centers = np.asarray(reference_facets["vectors"][missing_mask].mean(axis=1), dtype=float)
    metrics = {
        "reference_facet_count": int(len(reference_facets)),
        "design_facet_count": int(len(design_facets)),
        "raw_facet_count_delta": int(len(reference_facets) - len(design_facets)),
        "changed_reference_facet_count": int(missing_mask.sum()),
        "reference_hash_collisions": int(len(reference_hashes) - len(np.unique(reference_hashes))),
        "design_hash_collisions": int(len(design_hashes) - len(np.unique(design_hashes))),
    }
    del reference_facets, design_facets, reference_hashes, design_hashes
    return centers, metrics


def _cluster_surface_difference(centers: np.ndarray, mesh_extents: np.ndarray) -> dict[str, Any]:
    """Estimate spatial coverage of the CAD surface changes.

    This is a validation signal, not the final strut mapping.  It prevents an
    artifact from being accepted when the STL pair produces no usable spatial
    evidence at all.
    """

    if len(centers) == 0:
        return {
            "voxel_pitch": None,
            "cluster_count": 0,
            "clusters_with_50_or_more_facets": 0,
            "largest_cluster_facet_count": 0,
        }

    # About 160 bins across the shortest design dimension is detailed enough
    # to distinguish intentionally removed strut regions while staying light.
    pitch = float(np.min(mesh_extents) / 166.0)
    origin = centers.min(axis=0) - pitch
    indices = np.floor((centers - origin) / pitch).astype(int)
    shape = tuple((indices.max(axis=0) + 2).tolist())
    occupancy = np.zeros(shape, dtype=bool)
    occupancy[tuple(indices.T)] = True
    connected = ndimage.binary_dilation(
        occupancy,
        structure=np.ones((3, 3, 3), dtype=bool),
        iterations=1,
    )
    labels, cluster_count = ndimage.label(
        connected,
        structure=np.ones((3, 3, 3), dtype=bool),
    )
    label_per_facet = labels[tuple(indices.T)]
    facet_counts = np.bincount(label_per_facet, minlength=cluster_count + 1)[1:]
    return {
        "voxel_pitch": round(pitch, 6),
        "cluster_count": int(cluster_count),
        "clusters_with_50_or_more_facets": int(np.sum(facet_counts >= 50)),
        "largest_cluster_facet_count": int(facet_counts.max(initial=0)),
    }


def _signed_axis_permutations() -> Iterable[np.ndarray]:
    """All 48 axis-order/sign lattice symmetry candidates."""

    for order in permutations(range(3)):
        for signs in product((-1.0, 1.0), repeat=3):
            matrix = np.zeros((3, 3), dtype=float)
            for output_axis, input_axis in enumerate(order):
                matrix[output_axis, input_axis] = signs[output_axis]
            yield matrix


def _transform_points(
    points: np.ndarray,
    orientation: np.ndarray,
    nominal_center: np.ndarray,
    mesh_center: np.ndarray,
    output_scales: np.ndarray,
) -> np.ndarray:
    centered = points - nominal_center
    return (centered @ orientation.T) * output_scales + mesh_center


def _sample_strut_centerlines(endpoints: np.ndarray, samples_per_strut: int = 7) -> tuple[np.ndarray, np.ndarray]:
    fractions = np.linspace(0.12, 0.88, samples_per_strut)
    points = endpoints[:, :1, :] * (1.0 - fractions[None, :, None]) + endpoints[:, 1:, :] * fractions[None, :, None]
    strut_indexes = np.repeat(np.arange(len(endpoints), dtype=int), samples_per_strut)
    return points.reshape(-1, 3), strut_indexes


def _evaluate_symmetry_candidates(
    nominal: GraphGeometry,
    mesh_bounds: np.ndarray,
    changed_surface_centers: np.ndarray,
) -> list[dict[str, Any]]:
    """Fit bounds-based transforms and score sampled CAD-surface proximity."""

    if len(changed_surface_centers) == 0:
        return []

    nominal_points = nominal.endpoints.reshape(-1, 3)
    nominal_min = nominal_points.min(axis=0)
    nominal_max = nominal_points.max(axis=0)
    nominal_center = (nominal_min + nominal_max) / 2.0
    nominal_extents = nominal_max - nominal_min
    mesh_center = mesh_bounds.mean(axis=0)
    output_scales = (mesh_bounds[1] - mesh_bounds[0]) / nominal_extents
    samples, _ = _sample_strut_centerlines(nominal.endpoints, samples_per_strut=5)

    # A deterministic subsample holds the metric stable while limiting the
    # candidate evaluation to a sensible offline preprocessing time.
    max_points = 20_000
    if len(changed_surface_centers) > max_points:
        indexes = np.linspace(0, len(changed_surface_centers) - 1, max_points, dtype=int)
        evaluation_points = changed_surface_centers[indexes]
    else:
        evaluation_points = changed_surface_centers

    candidates = []
    for index, orientation in enumerate(_signed_axis_permutations()):
        transformed_samples = _transform_points(
            samples,
            orientation,
            nominal_center,
            mesh_center,
            output_scales,
        )
        tree = cKDTree(transformed_samples)
        distances, _ = tree.query(evaluation_points, k=1, workers=-1)
        candidates.append(
            {
                "candidate_index": index,
                "orientation": orientation.astype(int).tolist(),
                "scale": output_scales.round(8).tolist(),
                "translation": mesh_center.round(8).tolist(),
                "median_surface_to_centerline_distance": float(np.median(distances)),
                "p90_surface_to_centerline_distance": float(np.percentile(distances, 90)),
                "coverage_within_1_5_units": float(np.mean(distances <= 1.5)),
            }
        )

    return sorted(candidates, key=lambda item: item["median_surface_to_centerline_distance"])


def _validation_from_candidates(
    candidates: list[dict[str, Any]],
    graph_mapping: dict[str, Any],
    difference_metrics: dict[str, Any],
    cluster_metrics: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not graph_mapping["matching_ids"] or not graph_mapping["matching_topology"]:
        return STATUS_UNAVAILABLE, {
            "passed": False,
            "reason": "nominal_and_registered_graph_topology_do_not_match",
            "transform_confidence": 0.0,
            "mapping_coverage": 0.0,
        }
    if difference_metrics["changed_reference_facet_count"] == 0:
        return STATUS_VALIDATED, {
            "passed": True,
            "reason": "no_cad_omissions_detected",
            "transform_confidence": 1.0,
            "mapping_coverage": 1.0,
            "residual": 0.0,
        }
    if not candidates:
        return STATUS_UNAVAILABLE, {
            "passed": False,
            "reason": "no_registration_candidates",
            "transform_confidence": 0.0,
            "mapping_coverage": 0.0,
        }

    best = candidates[0]
    # Equal or near-equal candidates represent unresolved lattice symmetry.
    tolerance = max(0.02, best["median_surface_to_centerline_distance"] * 0.02)
    tied_candidates = [
        candidate
        for candidate in candidates
        if candidate["median_surface_to_centerline_distance"] <= best["median_surface_to_centerline_distance"] + tolerance
    ]
    mapping_coverage = best["coverage_within_1_5_units"]
    enough_spatial_evidence = cluster_metrics["clusters_with_50_or_more_facets"] > 0

    if len(tied_candidates) != 1:
        return STATUS_UNAVAILABLE, {
            "passed": False,
            "reason": "ambiguous_lattice_symmetry",
            "transform_confidence": 0.0,
            "mapping_coverage": mapping_coverage,
            "residual": best["median_surface_to_centerline_distance"],
            "equally_plausible_orientation_count": len(tied_candidates),
        }
    if mapping_coverage < 0.8 or not enough_spatial_evidence:
        return STATUS_UNAVAILABLE, {
            "passed": False,
            "reason": "insufficient_registration_coverage",
            "transform_confidence": 0.0,
            "mapping_coverage": mapping_coverage,
            "residual": best["median_surface_to_centerline_distance"],
        }
    return STATUS_VALIDATED, {
        "passed": True,
        "reason": "validated_unique_registration",
        "transform_confidence": 1.0,
        "mapping_coverage": mapping_coverage,
        "residual": best["median_surface_to_centerline_distance"],
        "equally_plausible_orientation_count": 1,
    }


def _classify_struts_with_mesh_proximity(
    nominal: GraphGeometry,
    design_stl: Path,
    candidate: dict[str, Any],
    expected_missing_count: int,
) -> tuple[list[int], dict[str, Any]]:
    """Classify CAD-present/omitted struts from sampled mesh-surface proximity.

    This expensive step is intentionally deferred until the transform itself
    has passed uniqueness validation.  It uses the paired design STL directly:
    present strut centerlines sit close to a mesh surface, while a removed
    strut's sampled centerline is appreciably farther away.
    """

    if expected_missing_count <= 0:
        return [], {
            "proximity_passed": True,
            "reason": "zero_expected_cad_omissions",
            "sample_count": 0,
        }

    import trimesh

    nominal_points = nominal.endpoints.reshape(-1, 3)
    nominal_center = (nominal_points.min(axis=0) + nominal_points.max(axis=0)) / 2.0
    orientation = np.asarray(candidate["orientation"], dtype=float)
    scales = np.asarray(candidate["scale"], dtype=float)
    translation = np.asarray(candidate["translation"], dtype=float)
    samples, _ = _sample_strut_centerlines(
        nominal.endpoints,
        samples_per_strut=5,
    )
    transformed_samples = _transform_points(
        samples,
        orientation,
        nominal_center,
        translation,
        scales,
    )

    mesh = trimesh.load_mesh(design_stl, process=False, maintain_order=True)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"{design_stl.name} did not load as a single triangular mesh")

    distances = np.empty(len(transformed_samples), dtype=float)
    # Chunking avoids a large temporary candidate-face array while rtree holds
    # the mesh acceleration structure once for all strut samples.
    chunk_size = 2_048
    for start in range(0, len(transformed_samples), chunk_size):
        stop = min(start + chunk_size, len(transformed_samples))
        _, chunk_distances, _ = trimesh.proximity.closest_point(
            mesh,
            transformed_samples[start:stop],
        )
        distances[start:stop] = chunk_distances
    del mesh

    per_strut_distance = np.median(
        distances.reshape(len(nominal.strut_ids), -1),
        axis=1,
    )

    ordered_indexes = np.argsort(per_strut_distance)
    expected_missing_count = min(expected_missing_count, len(ordered_indexes))
    omitted_indexes = ordered_indexes[-expected_missing_count:]
    present_indexes = ordered_indexes[:-expected_missing_count]
    omitted_distances = per_strut_distance[omitted_indexes]
    present_distances = per_strut_distance[present_indexes]
    boundary_gap = float(omitted_distances.min() - present_distances.max()) if len(present_distances) else math.inf
    present_median = float(np.median(present_distances)) if len(present_distances) else 0.0
    present_mad = float(np.median(np.abs(present_distances - present_median))) if len(present_distances) else 0.0
    minimum_required_gap = max(0.10, present_mad * 3.0)
    proximity_passed = bool(boundary_gap >= minimum_required_gap)
    return sorted(int(nominal.strut_ids[index]) for index in omitted_indexes), {
        "proximity_passed": proximity_passed,
        "reason": "validated_mesh_proximity" if proximity_passed else "no_clear_mesh_proximity_separation",
        "sample_count": int(len(transformed_samples)),
        "present_median_surface_distance": present_median,
        "present_mad_surface_distance": present_mad,
        "omitted_min_surface_distance": float(omitted_distances.min()),
        "boundary_gap": boundary_gap,
        "minimum_required_gap": minimum_required_gap,
    }


def _artifact_digest(artifact: dict[str, Any]) -> str:
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_design_intent_artifact(
    *,
    design_stl: Path,
    reference_stl: Path,
    nominal_graph: Path,
    registered_graph: Path,
    output_path: Path,
    expected_missing_rate_percent: float,
) -> dict[str, Any]:
    """Build a versioned design-intent artifact without touching CT evidence.

    A validated non-zero missing-strut map requires exactly one credible
    orientation.  The supplied 9x9x9 graph is highly symmetric, so an artifact
    can correctly be ``unavailable`` even when the CAD difference itself is
    clear.  The dashboard will then withhold source labels until a landmark or
    externally validated transform is supplied.
    """

    paths = (design_stl, reference_stl, nominal_graph, registered_graph)
    missing_paths = [str(path) for path in paths if not path.exists()]
    if missing_paths:
        raise FileNotFoundError(f"Required design-intent input not found: {', '.join(missing_paths)}")

    nominal, _ = _read_graph(nominal_graph)
    graph_mapping = _validate_graph_id_mapping(nominal_graph, registered_graph)
    design_mesh = _load_mesh_metadata(design_stl)
    reference_mesh = _load_mesh_metadata(reference_stl)
    changed_surface_centers, difference_metrics = _difference_facet_centers(reference_stl, design_stl)
    mesh_bounds = np.asarray(reference_mesh["bounds"], dtype=float)
    cluster_metrics = _cluster_surface_difference(
        changed_surface_centers,
        np.asarray(reference_mesh["extents"], dtype=float),
    )
    candidates = _evaluate_symmetry_candidates(nominal, mesh_bounds, changed_surface_centers)
    status, validation = _validation_from_candidates(
        candidates,
        graph_mapping,
        difference_metrics,
        cluster_metrics,
    )

    expected_omitted_strut_count = int(
        round(len(nominal.strut_ids) * expected_missing_rate_percent / 100.0)
    )
    # Mapping arbitrary graph IDs through an unresolved symmetry would be a
    # false claim.  Therefore only a validated, unique registration proceeds
    # to the final sampled mesh-proximity classification.
    intentional_missing_strut_ids: list[int] = []
    if status == STATUS_VALIDATED and expected_omitted_strut_count > 0:
        try:
            intentional_missing_strut_ids, proximity_metrics = _classify_struts_with_mesh_proximity(
                nominal,
                design_stl,
                candidates[0],
                expected_omitted_strut_count,
            )
            validation = {**validation, **proximity_metrics}
            if not proximity_metrics["proximity_passed"]:
                status = STATUS_UNAVAILABLE
                validation["passed"] = False
        except (OSError, ValueError, RuntimeError) as error:
            status = STATUS_UNAVAILABLE
            validation = {
                **validation,
                "passed": False,
                "reason": "mesh_proximity_classification_failed",
                "detail": str(error),
                "proximity_passed": False,
            }
            intentional_missing_strut_ids = []
    artifact: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "created_at": _utc_now(),
        "status": status,
        "mapping_status": status,
        "specimen": {
            "dataset": "0point5dash1",
            "expected_missing_rate_percent": expected_missing_rate_percent,
            "paired_design_stl": design_stl.name,
            "reference_stl": reference_stl.name,
        },
        "inputs": {
            "design_stl": _file_fingerprint(design_stl),
            "reference_stl": _file_fingerprint(reference_stl),
            "nominal_graph": _file_fingerprint(nominal_graph),
            "registered_graph": _file_fingerprint(registered_graph),
        },
        "graph_id_mapping": graph_mapping,
        "mesh_metadata": {
            "design": design_mesh,
            "reference": reference_mesh,
        },
        "cad_difference": {
            **difference_metrics,
            **cluster_metrics,
            "expected_omitted_strut_count": expected_omitted_strut_count,
        },
        "registration": {
            "best_candidate": candidates[0] if candidates else None,
            "candidate_count": len(candidates),
            "top_candidates": candidates[:8],
        },
        "validation": validation,
        "intentional_missing_strut_ids": intentional_missing_strut_ids,
    }
    artifact["artifact_sha256"] = _artifact_digest(artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output:
        json.dump(artifact, output, indent=2, sort_keys=True)
        output.write("\n")
    return artifact


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build validated CAD design-intent artifact")
    parser.add_argument("--design-stl", type=Path, required=True)
    parser.add_argument("--reference-stl", type=Path, required=True)
    parser.add_argument("--nominal-graph", type=Path, required=True)
    parser.add_argument("--registered-graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-missing-rate-percent", type=float, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = build_design_intent_artifact(
        design_stl=args.design_stl,
        reference_stl=args.reference_stl,
        nominal_graph=args.nominal_graph,
        registered_graph=args.registered_graph,
        output_path=args.output,
        expected_missing_rate_percent=args.expected_missing_rate_percent,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(args.output),
                "validation": result["validation"],
            },
            indent=2,
        )
    )
