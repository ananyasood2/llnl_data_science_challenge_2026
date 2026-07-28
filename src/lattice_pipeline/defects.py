"""Defect classification by comparing an aligned design graph with a CT scan.

The public :func:`classify_defects` function accepts design nodes/struts whose
coordinates have already been transformed into CT voxel coordinates.  Public
coordinates are always ``[x, y, z]``; NumPy volumes are indexed ``[z, y, x]``.
The function does not mutate its inputs and returns JSON-serialisable records.

This module intentionally uses full 26-connectivity for 3-D skeletons.  A
one-voxel-wide skeleton commonly joins diagonally; 6-connectivity therefore
creates thousands of artificial fragments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

STATUS_VALUES = frozenset(
    {"healthy", "missing", "thin", "thick", "broken", "disconnected", "uncertain"}
)


@dataclass(frozen=True)
class DefectConfig:
    """Tunable, physical-signal based classification thresholds.

    ``presence_radius_vox`` is the maximum centerline-to-skeleton distance used
    to say that a design sample is present.  It absorbs modest registration and
    skeletonisation error.  Missing and broken decisions use fractions of
    samples along a design strut, excluding a small region at either node.

    A design thickness should preferably be supplied on each strut as
    ``design_thickness_um``.  Otherwise ``nominal_thickness_um`` is used.
    Raw JSON ``thickness`` values are only converted when
    ``design_thickness_scale_mm`` is explicitly supplied, because the files do
    not define the physical unit of that field.
    """

    samples_per_voxel: float = 0.35
    min_samples: int = 16
    max_samples: int = 256
    endpoint_trim_fraction: float = 0.08
    presence_radius_vox: float = 5.0
    node_presence_radius_vox: float = 7.0
    missing_present_fraction: float = 0.22
    uncertain_missing_margin: float = 0.08
    broken_min_present_fraction: float = 0.25
    broken_max_present_fraction: float = 0.78
    endpoint_to_strut_radius_vox: float = 7.0
    endpoint_to_node_radius_vox: float = 7.0
    crop_margin_vox: float = 5.0
    min_disconnected_component_voxels: int = 10
    thin_ratio: float = 0.80
    thick_ratio: float = 1.25
    thickness_uncertain_band: float = 0.06
    edt_radius_correction_vox: float = 0.0
    nominal_thickness_um: float | None = 350.0
    design_thickness_scale_mm: float | None = None

    def __post_init__(self) -> None:
        if self.min_samples < 2 or self.max_samples < self.min_samples:
            raise ValueError("sample limits must satisfy 2 <= min_samples <= max_samples")
        if not 0 <= self.endpoint_trim_fraction < 0.5:
            raise ValueError("endpoint_trim_fraction must be in [0, 0.5)")
        for name in (
            "missing_present_fraction",
            "uncertain_missing_margin",
            "broken_min_present_fraction",
            "broken_max_present_fraction",
        ):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.thin_ratio >= 1 or self.thick_ratio <= 1:
            raise ValueError("thin_ratio must be < 1 and thick_ratio must be > 1")


def _xyz(record: Mapping[str, Any]) -> np.ndarray:
    if "position" in record:
        value = record["position"]
    elif all(axis in record for axis in ("x", "y", "z")):
        value = [record["x"], record["y"], record["z"]]
    else:
        raise ValueError(f"node {record.get('id', '?')} has no position or x/y/z fields")
    point = np.asarray(value, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError(f"invalid node position: {value!r}")
    return point


def _spacing_xyz(voxel_size_mm: float | Sequence[float]) -> np.ndarray:
    spacing = np.asarray(voxel_size_mm, dtype=float)
    if spacing.ndim == 0:
        spacing = np.repeat(spacing, 3)
    if spacing.shape != (3,) or np.any(~np.isfinite(spacing)) or np.any(spacing <= 0):
        raise ValueError("voxel_size_mm must be positive scalar or [x, y, z]")
    return spacing


def _json_number(value: float | np.number) -> float:
    return float(value) if np.isfinite(value) else 0.0


def _line_samples(a: np.ndarray, b: np.ndarray, cfg: DefectConfig) -> np.ndarray:
    length = float(np.linalg.norm(b - a))
    count = int(np.clip(np.ceil(length * cfg.samples_per_voxel), cfg.min_samples, cfg.max_samples))
    t = np.linspace(cfg.endpoint_trim_fraction, 1 - cfg.endpoint_trim_fraction, count)
    return a[None, :] + t[:, None] * (b - a)[None, :]


def _node_ids(strut: Mapping[str, Any]) -> tuple[Any, Any]:
    for keys in (("node_a", "node_b"), ("junction0", "junction1")):
        if keys[0] in strut and keys[1] in strut:
            return strut[keys[0]], strut[keys[1]]
    raise ValueError(f"strut {strut.get('id', '?')} has no endpoint node IDs")


def _design_thickness_um(strut: Mapping[str, Any], cfg: DefectConfig) -> float | None:
    if strut.get("design_thickness_um") is not None:
        return float(strut["design_thickness_um"])
    if strut.get("design_thickness_mm") is not None:
        return float(strut["design_thickness_mm"]) * 1000.0
    if strut.get("thickness_um") is not None:
        return float(strut["thickness_um"])
    if strut.get("thickness") is not None and cfg.design_thickness_scale_mm is not None:
        return float(strut["thickness"]) * cfg.design_thickness_scale_mm * 1000.0
    return cfg.nominal_thickness_um


def _severity(status: str, magnitude: float = 0.0) -> str:
    if status in {"missing", "broken", "disconnected"}:
        return "high"
    if status in {"thin", "thick"}:
        return "high" if magnitude >= 0.35 else "medium"
    return "low"


def _confidence_from_distance(value: float, cutoff: float, scale: float = 0.25) -> float:
    """Smooth confidence away from a cutoff, capped below absolute certainty."""
    width = max(abs(cutoff) * scale, 1e-6)
    return float(np.clip(0.5 + 0.48 * abs(value - cutoff) / width, 0.5, 0.98))


def _near_crop(point_xyz: np.ndarray, shape_zyx: Sequence[int], margin: float) -> bool:
    upper_xyz = np.asarray(shape_zyx[::-1], dtype=float) - 1
    return bool(np.any(point_xyz <= margin) or np.any(point_xyz >= upper_xyz - margin))


def _defect_record(
    defect_id: str,
    status: str,
    confidence: float,
    location_xyz: np.ndarray,
    spacing_xyz: np.ndarray,
    kind: str,
    element_id: Any,
    severity: str,
    size_value: float | None = None,
    size_unit: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "defect_id": defect_id,
        "type": status,
        "severity": severity,
        "confidence": round(float(np.clip(confidence, 0, 1)), 4),
        "location_voxel": [_json_number(v) for v in location_xyz],
        "location_mm": [_json_number(v) for v in location_xyz * spacing_xyz],
        "slice_index": int(np.clip(round(float(location_xyz[2])), 0, np.iinfo(np.int32).max)),
        "affected_element": {"kind": kind, "id": element_id},
        "size_metric": None,
    }
    if size_value is not None and size_unit is not None and np.isfinite(size_value):
        record["size_metric"] = {"value": round(float(size_value), 3), "unit": size_unit}
    if evidence:
        record["evidence"] = dict(evidence)
    return record


def _empty_spatial_index() -> tuple[cKDTree | None, np.ndarray]:
    return None, np.empty((0, 3), dtype=float)


def classify_defects(
    mask: np.ndarray,
    skeleton: np.ndarray,
    distance_map: np.ndarray,
    design_nodes: Iterable[Mapping[str, Any]],
    design_struts: Iterable[Mapping[str, Any]],
    voxel_size_mm: float | Sequence[float],
    *,
    config: DefectConfig | None = None,
) -> dict[str, Any]:
    """Classify aligned design elements and produce dashboard defect records.

    Parameters
    ----------
    mask, skeleton, distance_map:
        Equal-shaped ``[z, y, x]`` arrays. ``distance_map`` is the interior
        Euclidean distance in *voxels* (normally
        ``distance_transform_edt(mask)``); diameter is twice this value.
    design_nodes:
        Node mappings with ``id`` and either ``position: [x,y,z]`` or x/y/z.
        ``degree`` is optional and is derived from the design struts.
    design_struts:
        Strut mappings using either node_a/node_b or junction0/junction1.
        Coordinates must already be registered/aligned to the scan.
    voxel_size_mm:
        Scalar isotropic spacing or ``[x,y,z]`` spacing.  It controls all
        physical measurements, so rerunning this inexpensive classification
        makes the dashboard's editable voxel-size field reactive.

    Returns
    -------
    dict
        ``nodes``, ``struts``, ``components``, ``defects`` and ``summary``.
        Every node/strut has exactly one ``status``.  Low confidence is stored
        independently and never overwrites a specific status with uncertain.
    """
    cfg = config or DefectConfig()
    mask = np.asarray(mask, dtype=bool)
    skeleton = np.asarray(skeleton, dtype=bool)
    distance_map = np.asarray(distance_map)
    if mask.ndim != 3 or skeleton.shape != mask.shape or distance_map.shape != mask.shape:
        raise ValueError("mask, skeleton, and distance_map must be equal-shaped 3-D arrays")
    spacing = _spacing_xyz(voxel_size_mm)

    nodes_in = [dict(n) for n in design_nodes]
    struts_in = [dict(s) for s in design_struts]
    node_by_id = {n["id"]: n for n in nodes_in}
    if len(node_by_id) != len(nodes_in):
        raise ValueError("design node IDs must be unique")

    degrees = {node_id: 0 for node_id in node_by_id}
    endpoints_by_strut: list[tuple[Any, Any]] = []
    for strut in struts_in:
        a_id, b_id = _node_ids(strut)
        if a_id not in node_by_id or b_id not in node_by_id:
            raise ValueError(f"strut {strut.get('id', '?')} references an unknown node")
        degrees[a_id] += 1
        degrees[b_id] += 1
        endpoints_by_strut.append((a_id, b_id))

    # Full 26-connectivity is deliberate, not scipy.ndimage's 6-connected default.
    component_labels, component_count = ndimage.label(
        skeleton, structure=np.ones((3, 3, 3), dtype=np.uint8)
    )
    component_sizes = np.bincount(component_labels.ravel(), minlength=component_count + 1)
    main_label = int(np.argmax(component_sizes[1:]) + 1) if component_count else 0

    skeleton_zyx = np.argwhere(skeleton)
    if skeleton_zyx.size:
        skeleton_xyz = skeleton_zyx[:, ::-1].astype(float, copy=False)
        skeleton_tree: cKDTree | None = cKDTree(skeleton_xyz)
        skeleton_component = component_labels[tuple(skeleton_zyx.T)]
        skeleton_radius = distance_map[tuple(skeleton_zyx.T)]
    else:
        skeleton_tree, skeleton_xyz = _empty_spatial_index()
        skeleton_component = np.empty(0, dtype=np.int32)
        skeleton_radius = np.empty(0, dtype=float)

    neighbor_count = ndimage.convolve(
        skeleton.astype(np.uint8), np.ones((3, 3, 3), dtype=np.uint8), mode="constant"
    )
    endpoint_zyx = np.argwhere(skeleton & (neighbor_count == 2))  # includes center voxel
    if endpoint_zyx.size:
        endpoint_xyz = endpoint_zyx[:, ::-1].astype(float, copy=False)
        endpoint_tree: cKDTree | None = cKDTree(endpoint_xyz)
    else:
        endpoint_tree, endpoint_xyz = _empty_spatial_index()

    defects: list[dict[str, Any]] = []
    output_struts: list[dict[str, Any]] = []
    struts_per_component: dict[int, int] = {}

    for source, (a_id, b_id) in zip(struts_in, endpoints_by_strut):
        item = dict(source)
        item.setdefault("node_a", a_id)
        item.setdefault("node_b", b_id)
        a = _xyz(node_by_id[a_id])
        b = _xyz(node_by_id[b_id])
        samples = _line_samples(a, b, cfg)
        midpoint = (a + b) / 2

        if skeleton_tree is None:
            distances = np.full(len(samples), np.inf)
            nearest_idx = np.zeros(len(samples), dtype=int)
        else:
            distances, nearest_idx = skeleton_tree.query(samples, workers=1)
        # March through the segmented material itself.  The nearby skeleton is
        # an additional presence signal, not a replacement for the mask: small
        # skeleton gaps at junctions must not turn sound material into a
        # missing-strut result.
        mask_values = ndimage.map_coordinates(
            mask,
            [samples[:, 2], samples[:, 1], samples[:, 0]],
            order=0,
            mode="constant",
            cval=0,
            prefilter=False,
        ).astype(bool)
        skeleton_near = distances <= cfg.presence_radius_vox
        present = mask_values | skeleton_near
        present_fraction = float(np.mean(present))

        nearby_components = (
            skeleton_component[nearest_idx[skeleton_near]]
            if np.any(skeleton_near)
            else np.empty(0)
        )
        if nearby_components.size:
            labels, counts = np.unique(nearby_components, return_counts=True)
            component_id = int(labels[np.argmax(counts)])
            struts_per_component[component_id] = struts_per_component.get(component_id, 0) + 1
        else:
            component_id = None

        measured_um: float | None = None
        if np.any(skeleton_near):
            radii = np.asarray(skeleton_radius[nearest_idx[skeleton_near]], dtype=float)
            radii = radii[np.isfinite(radii) & (radii > 0)]
            if radii.size:
                # EDT is in voxels.  Mean axis spacing is a documented,
                # conservative approximation for anisotropic source data.
                measured_um = float(
                    2
                    * (np.median(radii) + cfg.edt_radius_correction_vox)
                    * np.mean(spacing)
                    * 1000
                )
        nominal_um = _design_thickness_um(item, cfg)
        thickness_ratio = (
            measured_um / nominal_um
            if measured_um is not None and nominal_um is not None and nominal_um > 0
            else None
        )

        interior_endpoint: np.ndarray | None = None
        if endpoint_tree is not None:
            endpoint_dist, endpoint_index = endpoint_tree.query(samples)
            candidates = np.flatnonzero(endpoint_dist <= cfg.endpoint_to_strut_radius_vox)
            if candidates.size:
                # Prefer the endpoint closest to the design centerline.
                best = candidates[np.argmin(endpoint_dist[candidates])]
                interior_endpoint = endpoint_xyz[int(endpoint_index[best])]

        status = "healthy"
        confidence = 1.0
        location = midpoint
        magnitude = 0.0

        if present_fraction < cfg.missing_present_fraction:
            status = "missing"
            confidence = _confidence_from_distance(
                present_fraction, cfg.missing_present_fraction, scale=0.6
            )
            location = samples[int(np.argmax(distances))]
        elif component_id is not None and main_label and component_id != main_label:
            # A present centerline belonging to any non-largest 26-connected
            # component is, by definition, a disconnected fragment.
            status = "disconnected"
            confidence = float(np.clip(0.65 + 0.33 * present_fraction, 0, 0.98))
        elif (
            present_fraction
            < cfg.missing_present_fraction + cfg.uncertain_missing_margin
            or (
                interior_endpoint is not None
                and _near_crop(interior_endpoint, mask.shape, cfg.crop_margin_vox)
            )
        ):
            status = "uncertain"
            confidence = 0.5
            location = interior_endpoint if interior_endpoint is not None else midpoint
        elif (
            interior_endpoint is not None
            and cfg.broken_min_present_fraction <= present_fraction <= cfg.broken_max_present_fraction
        ):
            status = "broken"
            confidence = float(
                np.clip(
                    0.6
                    + 0.35
                    * min(
                        (present_fraction - cfg.broken_min_present_fraction)
                        / max(cfg.broken_max_present_fraction - cfg.broken_min_present_fraction, 1e-6),
                        1,
                    ),
                    0,
                    0.95,
                )
            )
            location = interior_endpoint
        elif thickness_ratio is not None:
            magnitude = abs(thickness_ratio - 1)
            if thickness_ratio < cfg.thin_ratio:
                status = "thin"
                confidence = _confidence_from_distance(thickness_ratio, cfg.thin_ratio)
            elif thickness_ratio > cfg.thick_ratio:
                status = "thick"
                confidence = _confidence_from_distance(thickness_ratio, cfg.thick_ratio)
            elif (
                abs(thickness_ratio - cfg.thin_ratio) <= cfg.thickness_uncertain_band
                or abs(thickness_ratio - cfg.thick_ratio) <= cfg.thickness_uncertain_band
            ):
                status = "uncertain"
                confidence = 0.5

        item.update(
            {
                "status": status,
                "confidence": round(confidence, 4),
                "component_id": component_id,
                "measured_thickness_um": (
                    round(measured_um, 3) if measured_um is not None else None
                ),
                "design_thickness_um": round(nominal_um, 3) if nominal_um is not None else None,
                "present_fraction": round(present_fraction, 4),
                "polyline": [
                    [_json_number(v) for v in a],
                    [_json_number(v) for v in b],
                ],
            }
        )
        output_struts.append(item)
        if status != "healthy":
            defects.append(
                _defect_record(
                    f"d{len(defects) + 1:04d}",
                    status,
                    confidence,
                    location,
                    spacing,
                    "strut",
                    item.get("id"),
                    _severity(status, magnitude),
                    measured_um,
                    "um",
                    {
                        "present_fraction": round(present_fraction, 4),
                        "design_thickness_um": (
                            round(nominal_um, 3) if nominal_um is not None else None
                        ),
                    },
                )
            )

    # Node state uses the same skeleton index, but explicitly exempts legitimate
    # degree-one design boundary nodes from the broken-endpoint signal.
    output_nodes: list[dict[str, Any]] = []
    for source in nodes_in:
        item = dict(source)
        point = _xyz(item)
        degree = int(item.get("degree", degrees[item["id"]]))
        item["degree"] = degree
        if skeleton_tree is None:
            skeleton_distance, nearest_idx = np.inf, 0
        else:
            skeleton_distance, nearest_idx = skeleton_tree.query(point)
        rounded_zyx = np.rint(point[::-1]).astype(int)
        in_bounds = bool(
            np.all(rounded_zyx >= 0) and np.all(rounded_zyx < np.asarray(mask.shape))
        )
        mask_present = bool(mask[tuple(rounded_zyx)]) if in_bounds else False
        skeleton_near = bool(skeleton_distance <= cfg.node_presence_radius_vox)
        material_present = mask_present or skeleton_near
        component_id = int(skeleton_component[nearest_idx]) if skeleton_near else None
        endpoint_distance = (
            float(endpoint_tree.query(point)[0]) if endpoint_tree is not None else np.inf
        )

        status = "healthy"
        confidence = 1.0
        # Some graph files retain geometric helper/corner junctions that are
        # not referenced by any design strut. They are not expected material.
        if degree == 0:
            status = "healthy"
        # A degree-one node is an intentional outer boundary termination, not
        # evidence of a snapped strut merely because the skeleton stops nearby.
        elif degree == 1 and not material_present:
            status = "healthy"
            confidence = 0.85
        elif not material_present:
            status = "missing"
            confidence = float(np.clip(0.55 + 0.08 * (skeleton_distance - cfg.node_presence_radius_vox), 0.55, 0.98))
        elif component_id is not None and component_id != main_label and main_label:
            status = "disconnected"
            confidence = 0.9
        elif degree >= 2 and endpoint_distance <= cfg.endpoint_to_node_radius_vox:
            status = "uncertain" if _near_crop(point, mask.shape, cfg.crop_margin_vox) else "broken"
            confidence = 0.5 if status == "uncertain" else float(
                np.clip(0.95 - 0.4 * endpoint_distance / cfg.endpoint_to_node_radius_vox, 0.55, 0.95)
            )

        item.update(
            {
                "x": _json_number(point[0]),
                "y": _json_number(point[1]),
                "z": _json_number(point[2]),
                "status": status,
                "confidence": round(confidence, 4),
                "component_id": component_id,
            }
        )
        output_nodes.append(item)
        if status != "healthy":
            defects.append(
                _defect_record(
                    f"d{len(defects) + 1:04d}",
                    status,
                    confidence,
                    point,
                    spacing,
                    "node",
                    item.get("id"),
                    _severity(status),
                    skeleton_distance,
                    "voxel",
                    {"design_degree": degree},
                )
            )

    components = [
        {
            "id": component_id,
            "n_skeleton_voxels": int(component_sizes[component_id]),
            "n_struts": int(struts_per_component.get(component_id, 0)),
            "is_main": component_id == main_label,
        }
        for component_id in range(1, component_count + 1)
    ]
    # Preserve substantial scan fragments even when no expected design strut
    # can be mapped to them. Tiny one-to-three-voxel islands are segmentation
    # noise, not meaningful disconnected lattice regions.
    for component in components:
        if (
            component["is_main"]
            or component["n_skeleton_voxels"] < cfg.min_disconnected_component_voxels
            or component["n_struts"] > 0
        ):
            continue
        component_zyx = np.argwhere(component_labels == component["id"])
        location = np.mean(component_zyx, axis=0)[::-1]
        confidence = float(
            np.clip(
                0.65
                + 0.25
                * component["n_skeleton_voxels"]
                / max(cfg.min_disconnected_component_voxels * 4, 1),
                0.65,
                0.9,
            )
        )
        defects.append(
            _defect_record(
                f"d{len(defects) + 1:04d}",
                "disconnected",
                confidence,
                location,
                spacing,
                "component",
                component["id"],
                "high",
                component["n_skeleton_voxels"],
                "skeleton voxels",
                {"mapped_design_struts": 0},
            )
        )
    return {
        "nodes": output_nodes,
        "struts": output_struts,
        "components": components,
        "defects": defects,
        "summary": {
            "connected_components": int(component_count),
            "disconnected_regions": max(int(component_count) - (1 if main_label else 0), 0),
            "endpoint_count": int(len(endpoint_zyx)),
            "branch_point_count": int(np.count_nonzero(skeleton & (neighbor_count >= 4))),
            "connectivity": 26,
        },
    }


# A concise name for callers that treat the whole pipeline stage as an analysis.
analyze_defects = classify_defects


__all__ = [
    "DefectConfig",
    "STATUS_VALUES",
    "analyze_defects",
    "classify_defects",
]
