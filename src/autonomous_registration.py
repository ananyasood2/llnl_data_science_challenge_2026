"""Autonomous similarity registration of a nominal lattice graph to CT data.

This module deliberately does not read a pre-registered graph.  It detects
node-like regions from a raw CT TIFF, fits a global CAD-to-CT similarity
transform, performs local per-node refinement, and records every validation
needed to decide whether the resulting graph is safe for defect analysis.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from scipy import ndimage as ndi
from scipy.spatial import cKDTree


REGISTRATION_SCHEMA_VERSION = 1
DEFAULT_RANDOM_SEED = 20260728


@dataclass(frozen=True)
class RegistrationConfig:
    """Parameters for repeatable CAD-graph-to-CT registration."""

    threshold: int | None = None
    downsample_factor: int = 2
    downsample_phase_zyx: tuple[int, int, int] = (0, 0, 0)
    z_end_crop_fraction: float = 0.065
    edt_min_distance: float = 2.0
    component_min_voxels: int = 2
    component_max_voxels: int = 999
    fitting_fraction: float = 0.80
    trim_fraction: float = 0.70
    random_seed: int = DEFAULT_RANDOM_SEED
    max_icp_iterations: int = 60
    icp_improvement_tolerance: float = 1e-5
    heldout_median_distance_max: float = 8.0
    minimum_candidate_ratio: float = 0.20
    near_best_relative_tolerance: float = 0.02
    near_best_absolute_tolerance: float = 0.05
    transform_agreement_p95_max: float = 1.0
    stability_transform_p95_max: float = 3.0
    local_patch_half_width: int = 10
    local_search_radius: float = 8.0
    local_min_peak_radius: float = 2.0
    local_max_peak_radius: float = 32.0


@dataclass(frozen=True)
class SimilarityTransform:
    """CT point = scale * (CAD point @ rotation.T) + translation."""

    scale: float
    rotation: np.ndarray
    translation: np.ndarray

    def apply(self, points_xyz: np.ndarray) -> np.ndarray:
        return self.scale * (np.asarray(points_xyz, dtype=float) @ self.rotation.T) + self.translation

    def to_dict(self) -> dict[str, Any]:
        return {
            "scale": float(self.scale),
            "rotation": np.asarray(self.rotation, dtype=float).tolist(),
            "translation": np.asarray(self.translation, dtype=float).tolist(),
            "formula": "CT point = scale * (CAD point @ rotation.T) + translation",
        }


def load_cad_graph(graph_path: str | Path) -> tuple[dict[str, Any], np.ndarray, list[int]]:
    """Load and validate the nominal CAD junction cloud and graph connectivity."""

    path = Path(graph_path)
    with path.open("r", encoding="utf-8") as source:
        graph = json.load(source)
    junctions = graph.get("junctions")
    struts = graph.get("struts")
    if not isinstance(junctions, list) or not junctions:
        raise ValueError("CAD graph must contain a non-empty junctions list.")
    if not isinstance(struts, list) or not struts:
        raise ValueError("CAD graph must contain a non-empty struts list.")

    ids: list[int] = []
    points: list[np.ndarray] = []
    for junction in junctions:
        try:
            junction_id = int(junction["id"])
            position = np.asarray(junction["position"], dtype=float)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid CAD junction: {error}") from error
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError(f"CAD junction {junction_id} must have a finite XYZ position.")
        ids.append(junction_id)
        points.append(position)
    if len(set(ids)) != len(ids):
        raise ValueError("CAD graph contains duplicate junction IDs.")

    id_set = set(ids)
    for strut in struts:
        try:
            endpoint_ids = (int(strut["junction0"]), int(strut["junction1"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid CAD strut: {error}") from error
        if endpoint_ids[0] not in id_set or endpoint_ids[1] not in id_set:
            raise ValueError(f"CAD strut {strut.get('id')} references an unknown junction.")

    return graph, np.asarray(points, dtype=float), ids


def otsu_threshold_65536(tiff_path: str | Path) -> int:
    """Calculate an exact 65,536-bin Otsu threshold without loading the CT at once."""

    volume = tifffile.memmap(tiff_path)
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D CT TIFF; found shape {volume.shape}.")
    if not np.issubdtype(volume.dtype, np.integer) or np.iinfo(volume.dtype).bits > 16:
        raise ValueError(f"Exact 65,536-bin Otsu requires an integer TIFF up to 16 bits; found {volume.dtype}.")

    histogram = np.zeros(65536, dtype=np.int64)
    for start in range(0, volume.shape[0], 16):
        block = np.asarray(volume[start : start + 16], dtype=np.uint16)
        histogram += np.bincount(block.ravel(), minlength=65536)

    probabilities = histogram / histogram.sum()
    centers = np.arange(65536, dtype=float)
    cumulative_probability = np.cumsum(probabilities)
    cumulative_mean = np.cumsum(probabilities * centers)
    total_mean = cumulative_mean[-1]
    denominator = cumulative_probability * (1.0 - cumulative_probability)
    variance = np.zeros_like(cumulative_mean)
    valid = denominator > 0
    variance[valid] = (
        (total_mean * cumulative_probability[valid] - cumulative_mean[valid]) ** 2
        / denominator[valid]
    )
    return int(np.argmax(variance))


def detect_ct_junction_candidates(
    tiff_path: str | Path,
    threshold: int,
    config: RegistrationConfig,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Detect node-like CT regions using downsampling, EDT cores, and component size gates."""

    if config.downsample_factor < 1:
        raise ValueError("downsample_factor must be at least 1.")
    if len(config.downsample_phase_zyx) != 3:
        raise ValueError("downsample_phase_zyx must contain three values.")
    if not 0 <= config.z_end_crop_fraction < 0.5:
        raise ValueError("z_end_crop_fraction must be in [0, 0.5).")

    volume = tifffile.memmap(tiff_path)
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D CT TIFF; found shape {volume.shape}.")
    factor = config.downsample_factor
    phase = tuple(int(value) for value in config.downsample_phase_zyx)
    if any(value < 0 or value >= factor for value in phase):
        raise ValueError("Each downsample phase must be within [0, downsample_factor).")

    downsampled = np.asarray(
        volume[phase[0]::factor, phase[1]::factor, phase[2]::factor] >= threshold,
        dtype=bool,
    )
    crop_voxels = int(round(downsampled.shape[0] * config.z_end_crop_fraction))
    if crop_voxels:
        downsampled[:crop_voxels] = False
        downsampled[-crop_voxels:] = False

    distance = ndi.distance_transform_edt(downsampled)
    core = distance >= config.edt_min_distance
    labels, component_count = ndi.label(core)
    component_sizes = np.bincount(labels.ravel())
    accepted_labels = np.flatnonzero(
        (component_sizes >= config.component_min_voxels)
        & (component_sizes <= config.component_max_voxels)
    )
    accepted_labels = accepted_labels[accepted_labels != 0]
    centers_zyx = np.asarray(ndi.center_of_mass(core, labels, accepted_labels), dtype=float)
    if centers_zyx.size == 0:
        centers_xyz = np.empty((0, 3), dtype=float)
    else:
        offsets = np.asarray(phase, dtype=float)
        centers_xyz = (centers_zyx * factor + offsets)[..., [2, 1, 0]]

    nonzero_sizes = component_sizes[1:]
    diagnostics = {
        "threshold": int(threshold),
        "downsample_factor": factor,
        "downsample_phase_zyx": list(phase),
        "downsampled_shape_zyx": list(downsampled.shape),
        "z_end_crop_voxels": crop_voxels,
        "foreground_voxels": int(np.count_nonzero(downsampled)),
        "edt_min_distance": float(config.edt_min_distance),
        "component_count": int(component_count),
        "accepted_candidate_count": int(len(accepted_labels)),
        "accepted_component_size_quantiles": (
            np.quantile(component_sizes[accepted_labels], [0, 0.25, 0.5, 0.75, 1]).tolist()
            if len(accepted_labels)
            else []
        ),
        "component_size_quantiles": (
            np.quantile(nonzero_sizes, [0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1]).tolist()
            if len(nonzero_sizes)
            else []
        ),
    }
    return centers_xyz, diagnostics


def _rotation_matrix(axis: int, degrees: float) -> np.ndarray:
    radians = np.deg2rad(degrees)
    cosine = float(np.cos(radians))
    sine = float(np.sin(radians))
    if axis == 0:
        return np.array([[1, 0, 0], [0, cosine, -sine], [0, sine, cosine]], dtype=float)
    if axis == 1:
        return np.array([[cosine, 0, sine], [0, 1, 0], [-sine, 0, cosine]], dtype=float)
    if axis == 2:
        return np.array([[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1]], dtype=float)
    raise ValueError("Rotation axis must be 0, 1, or 2.")


def solve_similarity_transform(source_xyz: np.ndarray, target_xyz: np.ndarray) -> SimilarityTransform:
    """Fit scale, proper rotation, and translation using SVD/Umeyama alignment."""

    source = np.asarray(source_xyz, dtype=float)
    target = np.asarray(target_xyz, dtype=float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise ValueError("Similarity fitting requires matching Nx3 source and target arrays with N >= 3.")

    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    source_centered = source - source_center
    target_centered = target - target_center
    covariance = target_centered.T @ source_centered / len(source)
    left, singular_values, right_transposed = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(left @ right_transposed) < 0:
        correction[-1, -1] = -1
    rotation = left @ correction @ right_transposed
    source_variance = np.mean(np.sum(source_centered**2, axis=1))
    if source_variance <= np.finfo(float).eps:
        raise ValueError("Source correspondence cloud has zero variance.")
    scale = float(np.sum(singular_values * np.diag(correction)) / source_variance)
    translation = target_center - scale * (source_center @ rotation.T)
    return SimilarityTransform(scale=scale, rotation=rotation, translation=translation)


def trimmed_icp(
    source_xyz: np.ndarray,
    target_xyz: np.ndarray,
    initial_transform: SimilarityTransform,
    config: RegistrationConfig,
) -> dict[str, Any]:
    """Fit a similarity transform while discarding the most distant correspondences."""

    source = np.asarray(source_xyz, dtype=float)
    target = np.asarray(target_xyz, dtype=float)
    if len(target) < 3:
        raise ValueError("Trimmed ICP requires at least three CT candidates.")
    retained_count = max(3, int(np.floor(len(source) * config.trim_fraction)))
    if retained_count > len(source):
        raise ValueError("trim_fraction must not exceed 1.")

    tree = cKDTree(target)
    transform = initial_transform
    previous_rmse = np.inf
    for iteration in range(config.max_icp_iterations):
        transformed = transform.apply(source)
        distances, nearest_indices = tree.query(transformed, workers=-1)
        retained_indices = np.argpartition(distances, retained_count - 1)[:retained_count]
        transform = solve_similarity_transform(source[retained_indices], target[nearest_indices[retained_indices]])
        rmse = float(np.sqrt(np.mean(distances[retained_indices] ** 2)))
        if previous_rmse - rmse < config.icp_improvement_tolerance:
            break
        previous_rmse = rmse

    transformed = transform.apply(source)
    distances, nearest_indices = tree.query(transformed, workers=-1)
    retained_indices = np.argpartition(distances, retained_count - 1)[:retained_count]
    retained_distances = distances[retained_indices]
    return {
        "transform": transform,
        "rmse": float(np.sqrt(np.mean(retained_distances**2))),
        "median_nearest_distance": float(np.median(distances)),
        "p95_nearest_distance": float(np.percentile(distances, 95)),
        "retained_count": retained_count,
        "iterations": iteration + 1,
        "nearest_indices": nearest_indices,
    }


def fit_multistart_registration(
    cad_points_xyz: np.ndarray,
    fitting_candidates_xyz: np.ndarray,
    config: RegistrationConfig,
) -> list[dict[str, Any]]:
    """Run the prescribed 3-scale × 7-rotation trimmed ICP starts."""

    source = np.asarray(cad_points_xyz, dtype=float)
    target = np.asarray(fitting_candidates_xyz, dtype=float)
    source_span = np.ptp(source, axis=0)
    target_span = np.ptp(target, axis=0)
    if np.any(source_span <= 0) or np.any(target_span <= 0):
        raise ValueError("CAD and CT candidate clouds must span all three dimensions.")
    base_scale = float(np.median(target_span / source_span))
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    starts: list[tuple[float, int | None, float, SimilarityTransform]] = []
    rotation_starts = [(None, 0.0), (0, -1.0), (0, 1.0), (1, -1.0), (1, 1.0), (2, -1.0), (2, 1.0)]
    for scale_factor in (0.99, 1.0, 1.01):
        for axis, degrees in rotation_starts:
            rotation = np.eye(3) if axis is None else _rotation_matrix(axis, degrees)
            scale = base_scale * scale_factor
            translation = target_center - scale * (source_center @ rotation.T)
            starts.append((scale_factor, axis, degrees, SimilarityTransform(scale, rotation, translation)))

    results: list[dict[str, Any]] = []
    for scale_factor, axis, degrees, initial_transform in starts:
        result = trimmed_icp(source, target, initial_transform, config)
        result.update(
            {
                "initial_scale_factor": scale_factor,
                "initial_rotation_axis": axis,
                "initial_rotation_degrees": degrees,
                "initial_transform": initial_transform.to_dict(),
            }
        )
        results.append(result)
    results.sort(key=lambda result: result["rmse"])
    return results


def _split_ct_candidates(
    candidates_xyz: np.ndarray,
    config: RegistrationConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Create the fixed-seed 80/20 CT-candidate fitting/holdout split."""

    if len(candidates_xyz) < 4:
        raise ValueError("CT node detector produced fewer than four candidates.")
    random_generator = np.random.default_rng(config.random_seed)
    ordering = random_generator.permutation(len(candidates_xyz))
    split_index = int(round(len(candidates_xyz) * config.fitting_fraction))
    split_index = min(max(split_index, 3), len(candidates_xyz) - 1)
    return candidates_xyz[ordering[:split_index]], candidates_xyz[ordering[split_index:]]


def _transform_metrics(
    transform: SimilarityTransform,
    cad_points_xyz: np.ndarray,
    fitting_candidates_xyz: np.ndarray,
    heldout_candidates_xyz: np.ndarray,
    ct_shape_zyx: tuple[int, int, int],
    config: RegistrationConfig,
    fitting_tree: cKDTree | None = None,
) -> dict[str, Any]:
    """Measure one transform against fit-only and untouched holdout candidates."""

    predicted = transform.apply(cad_points_xyz)
    tree = fitting_tree if fitting_tree is not None else cKDTree(fitting_candidates_xyz)
    fitting_distances = tree.query(predicted, workers=-1)[0]
    retained_count = max(3, int(np.floor(len(fitting_distances) * config.trim_fraction)))
    retained = np.partition(fitting_distances, retained_count - 1)[:retained_count]
    heldout_distances = cKDTree(predicted).query(heldout_candidates_xyz, workers=-1)[0]
    shape_xyz = np.asarray(ct_shape_zyx, dtype=float)[[2, 1, 0]]
    inside = np.all((predicted >= 0) & (predicted < shape_xyz), axis=1)
    boundary_clearance = np.minimum(predicted, (shape_xyz - 1.0) - predicted)
    return {
        "trimmed_rmse": float(np.sqrt(np.mean(retained**2))),
        "median_nearest_distance": float(np.median(fitting_distances)),
        "p95_nearest_distance": float(np.percentile(fitting_distances, 95)),
        "heldout_median_distance": float(np.median(heldout_distances)),
        "inside_count": int(np.count_nonzero(inside)),
        "outside_indices": np.flatnonzero(~inside).astype(int).tolist(),
        "bounds_xyz": {
            "min": predicted.min(axis=0).tolist(),
            "max": predicted.max(axis=0).tolist(),
        },
        "minimum_ct_boundary_clearance_voxels": float(np.min(boundary_clearance)),
    }


def infer_nearby_lattice_symmetry_offsets(cad_points_xyz: np.ndarray) -> list[tuple[int, int, int]]:
    """Return nearby integer translations that preserve the CAD node parity basis.

    Periodic lattices can give trimmed ICP several equally good translations.
    This derives the permitted local translations from the nominal CAD graph's
    integer node grid; it does not inspect another registered graph.
    """

    points = np.asarray(cad_points_xyz, dtype=float)
    rounded = np.rint(points).astype(int)
    if not np.allclose(points, rounded, atol=1e-6):
        return [(0, 0, 0)]
    parity_basis = {tuple(row) for row in np.mod(rounded, 2)}
    offsets: list[tuple[int, int, int]] = []
    for offset in product((-1, 0, 1), repeat=3):
        translated_basis = {
            tuple(np.mod(np.asarray(parity, dtype=int) + np.asarray(offset, dtype=int), 2))
            for parity in parity_basis
        }
        if translated_basis == parity_basis:
            offsets.append(tuple(int(value) for value in offset))
    return offsets or [(0, 0, 0)]


def resolve_lattice_translation_symmetry(
    baseline_transform: SimilarityTransform,
    cad_points_xyz: np.ndarray,
    fitting_candidates_xyz: np.ndarray,
    heldout_candidates_xyz: np.ndarray,
    ct_shape_zyx: tuple[int, int, int],
    config: RegistrationConfig,
) -> tuple[SimilarityTransform, dict[str, Any]]:
    """Resolve periodic translation aliases using fit-only score and FOV safety.

    An offset is considered only when it preserves the detected nominal node
    parity basis. To prevent an arbitrary visually convenient shift, it must
    put every CAD junction in the CT volume and meet the untouched holdout
    criterion. Periodic candidates can otherwise have near-identical ICP
    scores, so the primary tie-breaker maximizes the minimum clearance to the
    finite CT boundary; that picks the complete specimen placement rather than
    a same-pattern, one-cell-shifted alias. Fit-only trimmed RMSE is the next
    tie-breaker. If no candidate is eligible, the original ICP result is
    retained and validation will fail normally.
    """

    fitting_tree = cKDTree(fitting_candidates_xyz)
    offsets = infer_nearby_lattice_symmetry_offsets(cad_points_xyz)
    basis_vectors_xyz = baseline_transform.scale * baseline_transform.rotation
    candidates: list[tuple[SimilarityTransform, dict[str, Any]]] = []
    for offset in offsets:
        translation = baseline_transform.translation + np.asarray(offset, dtype=float) @ basis_vectors_xyz.T
        transform = SimilarityTransform(
            scale=baseline_transform.scale,
            rotation=baseline_transform.rotation,
            translation=translation,
        )
        metrics = _transform_metrics(
            transform,
            cad_points_xyz,
            fitting_candidates_xyz,
            heldout_candidates_xyz,
            ct_shape_zyx,
            config,
            fitting_tree,
        )
        metrics["offset_cad_xyz"] = list(offset)
        metrics["eligible"] = bool(
            metrics["inside_count"] == len(cad_points_xyz)
            and metrics["heldout_median_distance"] <= config.heldout_median_distance_max
        )
        candidates.append((transform, metrics))

    eligible = [(transform, metrics) for transform, metrics in candidates if metrics["eligible"]]
    if eligible:
        selected_transform, selected_metrics = min(
            eligible,
            key=lambda item: (
                -item[1]["minimum_ct_boundary_clearance_voxels"],
                item[1]["trimmed_rmse"],
                item[1]["heldout_median_distance"],
                item[1]["offset_cad_xyz"],
            ),
        )
        selection_reason = (
            "maximum_minimum_ct_boundary_clearance_then_lowest_fit_only_trimmed_rmse_"
            "among_fov_and_holdout_eligible_symmetries"
        )
    else:
        selected_transform, selected_metrics = candidates[0]
        selection_reason = "no_fov_and_holdout_eligible_symmetry; retained_baseline_icp_transform"

    return selected_transform, {
        "method": "nearby_nominal_node_parity_symmetry_resolution",
        "candidate_count": len(candidates),
        "selection_reason": selection_reason,
        "selected_offset_cad_xyz": selected_metrics["offset_cad_xyz"],
        "selected_metrics": selected_metrics,
        "candidates": [metrics for _, metrics in candidates],
    }


def select_and_validate_transform(
    results: list[dict[str, Any]],
    cad_points_xyz: np.ndarray,
    fitting_candidates_xyz: np.ndarray,
    heldout_candidates_xyz: np.ndarray,
    ct_shape_zyx: tuple[int, int, int],
    candidate_count: int,
    config: RegistrationConfig,
) -> tuple[SimilarityTransform, dict[str, Any]]:
    """Select the best ICP result and calculate fit, agreement, holdout, and FOV checks."""

    if not results:
        raise ValueError("No ICP results were produced.")
    best = results[0]
    best_rmse = float(best["rmse"])
    near_limit = best_rmse + max(
        config.near_best_absolute_tolerance,
        best_rmse * config.near_best_relative_tolerance,
    )
    near_best = [result for result in results if result["rmse"] <= near_limit]
    agreeing_results = near_best[: min(5, len(near_best))]
    agreement_p95: list[float] = []
    predicted_clouds = [result["transform"].apply(cad_points_xyz) for result in agreeing_results]
    for left_index in range(len(predicted_clouds)):
        for right_index in range(left_index + 1, len(predicted_clouds)):
            separation = np.linalg.norm(predicted_clouds[left_index] - predicted_clouds[right_index], axis=1)
            agreement_p95.append(float(np.percentile(separation, 95)))

    transform = best["transform"]
    metrics = _transform_metrics(
        transform,
        cad_points_xyz,
        fitting_candidates_xyz,
        heldout_candidates_xyz,
        ct_shape_zyx,
        config,
    )
    candidate_ratio = candidate_count / len(cad_points_xyz)
    validation = {
        "best_rmse": metrics["trimmed_rmse"],
        "best_median_nearest_distance": metrics["median_nearest_distance"],
        "best_p95_nearest_distance": metrics["p95_nearest_distance"],
        "near_best_count": len(near_best),
        "near_best_required": 3,
        "near_best_agreement_p95_voxels": max(agreement_p95, default=float("inf")),
        "near_best_agreement_p95_max_voxels": config.transform_agreement_p95_max,
        "heldout_candidate_count": int(len(heldout_candidates_xyz)),
        "heldout_median_distance_voxels": metrics["heldout_median_distance"],
        "heldout_median_distance_max_voxels": config.heldout_median_distance_max,
        "candidate_count": int(candidate_count),
        "candidate_ratio_to_cad_nodes": float(candidate_ratio),
        "minimum_candidate_ratio": config.minimum_candidate_ratio,
        "all_cad_nodes_inside_ct": metrics["inside_count"] == len(cad_points_xyz),
        "inside_cad_node_count": metrics["inside_count"],
        "outside_cad_node_count": len(metrics["outside_indices"]),
        "outside_cad_node_indices": metrics["outside_indices"],
        "transformed_bounds_xyz": metrics["bounds_xyz"],
    }
    validation["core_checks_passed"] = bool(
        validation["near_best_count"] >= validation["near_best_required"]
        and validation["near_best_agreement_p95_voxels"] <= config.transform_agreement_p95_max
        and validation["heldout_median_distance_voxels"] <= config.heldout_median_distance_max
        and validation["candidate_ratio_to_cad_nodes"] >= config.minimum_candidate_ratio
        and validation["all_cad_nodes_inside_ct"]
    )
    return transform, validation


def synthetic_recovery_check() -> dict[str, Any]:
    """Exercise the robust ICP implementation with fixed synthetic correspondences and outliers."""

    rng = np.random.default_rng(104729)
    source = rng.uniform(-5, 5, size=(300, 3))
    truth = SimilarityTransform(
        scale=37.25,
        rotation=_rotation_matrix(2, 4.0) @ _rotation_matrix(1, -2.0),
        translation=np.array([120.0, 75.0, 44.0]),
    )
    target = truth.apply(source) + rng.normal(0, 0.08, size=source.shape)
    target = np.vstack((target[rng.random(len(target)) > 0.2], rng.uniform(0, 250, size=(90, 3))))
    initial = SimilarityTransform(
        scale=truth.scale * 0.995,
        rotation=_rotation_matrix(0, 0.8) @ truth.rotation,
        translation=truth.translation + np.array([0.5, -0.5, 0.3]),
    )
    config = RegistrationConfig(trim_fraction=0.70, max_icp_iterations=60)
    result = trimmed_icp(source, target, initial, config)
    predicted = result["transform"].apply(source)
    error = np.linalg.norm(predicted - truth.apply(source), axis=1)
    p95_error = float(np.percentile(error, 95))
    return {
        "p95_recovery_error_voxels": p95_error,
        "rmse": float(result["rmse"]),
        "passed": bool(p95_error <= 0.5),
    }


def _fit_from_candidates(
    cad_points_xyz: np.ndarray,
    candidates_xyz: np.ndarray,
    ct_shape_zyx: tuple[int, int, int],
    config: RegistrationConfig,
) -> tuple[SimilarityTransform, dict[str, Any], list[dict[str, Any]]]:
    fitting_candidates, heldout_candidates = _split_ct_candidates(candidates_xyz, config)
    results = fit_multistart_registration(cad_points_xyz, fitting_candidates, config)
    transform, validation = select_and_validate_transform(
        results,
        cad_points_xyz,
        fitting_candidates,
        heldout_candidates,
        ct_shape_zyx,
        len(candidates_xyz),
        config,
    )
    transform, symmetry = resolve_lattice_translation_symmetry(
        transform,
        cad_points_xyz,
        fitting_candidates,
        heldout_candidates,
        ct_shape_zyx,
        config,
    )
    selected_metrics = symmetry["selected_metrics"]
    validation.update(
        {
            "best_rmse": selected_metrics["trimmed_rmse"],
            "best_median_nearest_distance": selected_metrics["median_nearest_distance"],
            "best_p95_nearest_distance": selected_metrics["p95_nearest_distance"],
            "heldout_median_distance_voxels": selected_metrics["heldout_median_distance"],
            "all_cad_nodes_inside_ct": selected_metrics["inside_count"] == len(cad_points_xyz),
            "inside_cad_node_count": selected_metrics["inside_count"],
            "outside_cad_node_count": len(selected_metrics["outside_indices"]),
            "outside_cad_node_indices": selected_metrics["outside_indices"],
            "transformed_bounds_xyz": selected_metrics["bounds_xyz"],
            "symmetry_resolution": symmetry,
        }
    )
    validation["core_checks_passed"] = bool(
        validation["near_best_count"] >= validation["near_best_required"]
        and validation["near_best_agreement_p95_voxels"] <= config.transform_agreement_p95_max
        and validation["heldout_median_distance_voxels"] <= config.heldout_median_distance_max
        and validation["candidate_ratio_to_cad_nodes"] >= config.minimum_candidate_ratio
        and validation["all_cad_nodes_inside_ct"]
    )
    validation["fitting_candidate_count"] = int(len(fitting_candidates))
    return transform, validation, results


def stability_checks(
    tiff_path: str | Path,
    threshold: int,
    cad_points_xyz: np.ndarray,
    baseline_transform: SimilarityTransform,
    config: RegistrationConfig,
) -> dict[str, Any]:
    """Repeat registration under threshold, sampling, EDT, trim, and seed perturbations."""

    volume = tifffile.memmap(tiff_path)
    threshold_delta = max(1, int(round((np.iinfo(volume.dtype).max - np.iinfo(volume.dtype).min) * 0.01)))
    variants = [
        ("threshold_minus_1_percent", replace(config, threshold=threshold - threshold_delta)),
        ("threshold_plus_1_percent", replace(config, threshold=threshold + threshold_delta)),
        ("downsample_phase_111", replace(config, downsample_phase_zyx=(1, 1, 1))),
        ("edt_low_1p8", replace(config, edt_min_distance=1.8)),
        ("edt_high_2p2", replace(config, edt_min_distance=2.2)),
        ("trim_65_percent", replace(config, trim_fraction=0.65)),
        ("trim_75_percent", replace(config, trim_fraction=0.75)),
        ("alternate_random_seed", replace(config, random_seed=config.random_seed + 1)),
    ]
    baseline_points = baseline_transform.apply(cad_points_xyz)
    results: list[dict[str, Any]] = []
    # Trim-fraction and RNG variants must use the original detector output.
    # Reusing one of the EDT-perturbed clouds here would make these checks
    # measure two changes at once and hide (or invent) instability.
    cached_candidates, cached_diagnostics = detect_ct_junction_candidates(
        tiff_path,
        threshold,
        config,
    )
    for name, variant in variants:
        needs_detection = name not in {"trim_65_percent", "trim_75_percent", "alternate_random_seed"}
        try:
            if needs_detection:
                effective_threshold = variant.threshold if variant.threshold is not None else threshold
                candidates, diagnostics = detect_ct_junction_candidates(tiff_path, effective_threshold, variant)
            else:
                candidates, diagnostics = cached_candidates, cached_diagnostics
            transform, validation, _ = _fit_from_candidates(
                cad_points_xyz,
                candidates,
                tuple(volume.shape),
                variant,
            )
            difference = np.linalg.norm(transform.apply(cad_points_xyz) - baseline_points, axis=1)
            results.append(
                {
                    "name": name,
                    "passed": bool(np.percentile(difference, 95) <= config.stability_transform_p95_max),
                    "transform_difference_p50_voxels": float(np.median(difference)),
                    "transform_difference_p95_voxels": float(np.percentile(difference, 95)),
                    "candidate_count": int(len(candidates)),
                    "core_checks_passed": validation["core_checks_passed"],
                    "selected_symmetry_offset_cad_xyz": validation["symmetry_resolution"][
                        "selected_offset_cad_xyz"
                    ],
                    "selected_minimum_ct_boundary_clearance_voxels": validation[
                        "symmetry_resolution"
                    ]["selected_metrics"]["minimum_ct_boundary_clearance_voxels"],
                    "detector": diagnostics,
                }
            )
        except (OSError, ValueError, RuntimeError, np.linalg.LinAlgError) as error:
            results.append({"name": name, "passed": False, "error": str(error)})
    return {
        "transform_difference_p95_max_voxels": config.stability_transform_p95_max,
        "variants": results,
        "passed": bool(results and all(result["passed"] for result in results)),
    }


def refine_registered_nodes(
    tiff_path: str | Path,
    threshold: int,
    coarse_points_xyz: np.ndarray,
    config: RegistrationConfig,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, int]]:
    """Refine each coarse point in a 21³ patch without performing another global fit."""

    volume = tifffile.memmap(tiff_path)
    shape_zyx = np.asarray(volume.shape, dtype=int)
    refined = np.asarray(coarse_points_xyz, dtype=float).copy()
    records: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    half_width = config.local_patch_half_width
    for index, coarse_xyz in enumerate(coarse_points_xyz):
        coarse_zyx = np.asarray(coarse_xyz, dtype=float)[[2, 1, 0]]
        rounded_zyx = np.rint(coarse_zyx).astype(int)
        lower = rounded_zyx - half_width
        upper = rounded_zyx + half_width + 1
        if np.any(lower < 0) or np.any(upper > shape_zyx):
            status = "outside_or_edge_clipped"
            record = {"status": status, "shift_voxels": None, "peak_radius_voxels": None}
        else:
            patch = np.asarray(
                volume[lower[0]:upper[0], lower[1]:upper[1], lower[2]:upper[2]] >= threshold,
                dtype=bool,
            )
            distance = ndi.distance_transform_edt(patch)
            peak_radius = float(distance.max())
            if not config.local_min_peak_radius <= peak_radius <= config.local_max_peak_radius:
                status = "implausible_peak_radius"
                record = {"status": status, "shift_voxels": None, "peak_radius_voxels": peak_radius}
            else:
                near_peak = distance >= peak_radius * 0.92
                peak_labels, peak_component_count = ndi.label(near_peak)
                viable_components = 0
                for label in range(1, peak_component_count + 1):
                    if float(distance[peak_labels == label].max()) >= peak_radius * 0.95:
                        viable_components += 1
                if viable_components > 1:
                    status = "ambiguous_double_peak"
                    record = {"status": status, "shift_voxels": None, "peak_radius_voxels": peak_radius}
                else:
                    peak_zyx = np.argwhere(distance == peak_radius)[0].astype(float)
                    coordinates = np.argwhere(distance >= max(1.0, peak_radius * 0.5)).astype(float)
                    coordinates = coordinates[
                        np.linalg.norm(coordinates - peak_zyx, axis=1) <= 3.0
                    ]
                    weights = distance[tuple(coordinates.astype(int).T)] ** 2
                    local_center_zyx = np.average(coordinates, axis=0, weights=weights)
                    refined_zyx = lower + local_center_zyx
                    shift = float(np.linalg.norm(refined_zyx - coarse_zyx))
                    if shift > config.local_search_radius:
                        status = "shift_exceeds_search_radius"
                        record = {"status": status, "shift_voxels": shift, "peak_radius_voxels": peak_radius}
                    else:
                        refined[index] = refined_zyx[[2, 1, 0]]
                        status = "refined"
                        record = {"status": status, "shift_voxels": shift, "peak_radius_voxels": peak_radius}
        records.append(record)
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
    return refined, records, status_counts


def build_registered_graph(
    cad_graph: dict[str, Any],
    coarse_points_xyz: np.ndarray,
    refined_points_xyz: np.ndarray,
    refinement_records: list[dict[str, Any]],
    registration_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Apply registration coordinates to junctions while preserving all IDs and strut links."""

    registered = copy.deepcopy(cad_graph)
    for junction, coarse, refined, refinement in zip(
        registered["junctions"],
        coarse_points_xyz,
        refined_points_xyz,
        refinement_records,
        strict=True,
    ):
        original_position = list(junction["position"])
        junction["cad_position"] = original_position
        junction["position"] = np.round(refined, 6).tolist()
        junction["registration"] = {
            "coarse_position": np.round(coarse, 6).tolist(),
            **refinement,
        }
    registered["registration"] = registration_metadata
    return registered


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    """Write a JSON artifact atomically in its destination directory."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{destination.stem}.", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.write("\n")
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def run_autonomous_registration(
    cad_graph_path: str | Path,
    tiff_path: str | Path,
    config: RegistrationConfig | None = None,
    *,
    run_stability: bool = True,
    refine_nodes: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the complete autonomous registration workflow without a registered-JSON input."""

    config = config or RegistrationConfig()
    cad_graph, cad_points_xyz, junction_ids = load_cad_graph(cad_graph_path)
    threshold = config.threshold if config.threshold is not None else otsu_threshold_65536(tiff_path)
    candidates_xyz, detector = detect_ct_junction_candidates(tiff_path, threshold, config)
    volume = tifffile.memmap(tiff_path)
    transform, validation, icp_results = _fit_from_candidates(
        cad_points_xyz,
        candidates_xyz,
        tuple(volume.shape),
        config,
    )
    synthetic = synthetic_recovery_check()
    stability = (
        stability_checks(tiff_path, threshold, cad_points_xyz, transform, config)
        if run_stability
        else {"skipped": True, "passed": None, "variants": []}
    )
    coarse_points_xyz = transform.apply(cad_points_xyz)
    if refine_nodes:
        refined_points_xyz, refinement_records, refinement_summary = refine_registered_nodes(
            tiff_path,
            threshold,
            coarse_points_xyz,
            config,
        )
    else:
        refined_points_xyz = coarse_points_xyz.copy()
        refinement_records = [
            {"status": "not_requested", "shift_voxels": None, "peak_radius_voxels": None}
            for _ in coarse_points_xyz
        ]
        refinement_summary = {"not_requested": len(coarse_points_xyz)}

    validation["synthetic_recovery"] = synthetic
    validation["stability"] = stability
    validation["strict_passed"] = bool(
        validation["core_checks_passed"]
        and synthetic["passed"]
        and (stability.get("passed") is True or stability.get("skipped") is True)
    )
    validation["status"] = "validated" if validation["strict_passed"] else "provisional"
    registration_metadata = {
        "schema_version": REGISTRATION_SCHEMA_VERSION,
        "coordinate_source": "nominal_cad_graph_plus_raw_ct_tiff",
        "transform": transform.to_dict(),
        "threshold": int(threshold),
        "config": asdict(config),
        "validation": validation,
        "refinement_summary": refinement_summary,
        "cad_junction_ids": junction_ids,
    }
    registered_graph = build_registered_graph(
        cad_graph,
        coarse_points_xyz,
        refined_points_xyz,
        refinement_records,
        registration_metadata,
    )
    audit = {
        "schema_version": REGISTRATION_SCHEMA_VERSION,
        "cad_graph_path": str(Path(cad_graph_path)),
        "ct_tiff_path": str(Path(tiff_path)),
        "threshold": int(threshold),
        "detector": detector,
        "transform": transform.to_dict(),
        "validation": validation,
        "refinement_summary": refinement_summary,
        "multistart_results": [
            {
                "rmse": float(result["rmse"]),
                "median_nearest_distance": float(result["median_nearest_distance"]),
                "p95_nearest_distance": float(result["p95_nearest_distance"]),
                "retained_count": int(result["retained_count"]),
                "iterations": int(result["iterations"]),
                "initial_scale_factor": float(result["initial_scale_factor"]),
                "initial_rotation_axis": result["initial_rotation_axis"],
                "initial_rotation_degrees": float(result["initial_rotation_degrees"]),
                "transform": result["transform"].to_dict(),
            }
            for result in icp_results
        ],
    }
    return registered_graph, audit
