"""Deterministic lattice thickness and relative-density measurements.

This module contains scientific calculations only.  Browser, MCP, and language
model layers must consume these results rather than recomputing their values.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


MEASUREMENT_METHOD_VERSION = "1"
DEFAULT_POLICY_VERSION = "demo-policy-v1"


def _positive_number(value: float, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero")
    return number


def _valid_thickness(record: Mapping[str, Any]) -> float | None:
    value = record.get("measured_thickness_um")
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and number > 0 else None


def compute_thickness_histogram(
    thickness_values_um: Sequence[float] | np.ndarray,
    *,
    target_um: float = 350.0,
    bin_count: int = 24,
) -> dict[str, Any]:
    """Return target-focused histogram bins while retaining overflow counts."""

    target = _positive_number(target_um, "target_um")
    if bin_count < 5 or bin_count > 100:
        raise ValueError("bin_count must be between 5 and 100")
    values = np.asarray(thickness_values_um, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return {
            "bin_count": bin_count,
            "range_min_um": 0.0,
            "range_max_um": target * 2,
            "bins": [],
            "overflow_count": 0,
        }

    display_max = max(target * 2, float(np.quantile(values, 0.95)))
    display_values = values[values <= display_max]
    counts, edges = np.histogram(display_values, bins=bin_count, range=(0.0, display_max))
    bins = [
        {
            "start_um": round(float(edges[index]), 3),
            "end_um": round(float(edges[index + 1]), 3),
            "count": int(counts[index]),
        }
        for index in range(len(counts))
    ]
    return {
        "bin_count": bin_count,
        "range_min_um": 0.0,
        "range_max_um": round(display_max, 3),
        "bins": bins,
        "overflow_count": int(np.count_nonzero(values > display_max)),
    }


def compute_thickness_summary(
    struts: Iterable[Mapping[str, Any]],
    *,
    target_um: float = 350.0,
    critical_cutoff_um: float = 300.0,
    user_cutoff_um: float | None = None,
    histogram_bins: int = 24,
) -> dict[str, Any]:
    """Summarize recorded strut thicknesses with explicit eligibility counts."""

    target = _positive_number(target_um, "target_um")
    critical = _positive_number(critical_cutoff_um, "critical_cutoff_um")
    user_cutoff = _positive_number(
        target if user_cutoff_um is None else user_cutoff_um,
        "user_cutoff_um",
    )
    records = list(struts)
    eligible: list[tuple[Mapping[str, Any], float]] = []
    for record in records:
        thickness = _valid_thickness(record)
        if thickness is not None:
            eligible.append((record, thickness))
    if not eligible:
        raise ValueError("No struts have a finite positive measured_thickness_um value")

    values = np.asarray([value for _, value in eligible], dtype=float)
    status_counts = Counter(str(record.get("status", "unknown")) for record, _ in eligible)

    def below(cutoff: float) -> dict[str, Any]:
        count = int(np.count_nonzero(values < cutoff))
        return {
            "cutoff_um": round(cutoff, 3),
            "count": count,
            "percent": round(100.0 * count / values.size, 3),
        }

    return {
        "unit": "um",
        "method": "skeleton_edt_median_diameter",
        "method_version": MEASUREMENT_METHOD_VERSION,
        "eligibility_rule": "finite positive measured_thickness_um",
        "total_strut_count": len(records),
        "eligible_strut_count": int(values.size),
        "excluded_strut_count": len(records) - int(values.size),
        "eligible_status_counts": dict(sorted(status_counts.items())),
        "target_um": round(target, 3),
        "critical_cutoff_um": round(critical, 3),
        "user_cutoff_um": round(user_cutoff, 3),
        "mean_um": round(float(np.mean(values)), 3),
        "median_um": round(float(np.median(values)), 3),
        "min_um": round(float(np.min(values)), 3),
        "max_um": round(float(np.max(values)), 3),
        "standard_deviation_um": round(float(np.std(values)), 3),
        "below_target": below(target),
        "below_critical": below(critical),
        "below_user_cutoff": below(user_cutoff),
        "histogram": compute_thickness_histogram(
            values,
            target_um=target,
            bin_count=histogram_bins,
        ),
    }


def list_out_of_spec_struts(
    struts: Iterable[Mapping[str, Any]],
    *,
    cutoff_um: float,
    limit: int = 25,
) -> dict[str, Any]:
    """Rank measured struts below a cutoff from thinnest upward."""

    cutoff = _positive_number(cutoff_um, "cutoff_um")
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    matches: list[dict[str, Any]] = []
    for record in struts:
        thickness = _valid_thickness(record)
        if thickness is None or thickness >= cutoff:
            continue
        matches.append(
            {
                "strut_id": record.get("id"),
                "measured_thickness_um": round(thickness, 3),
                "difference_from_cutoff_um": round(thickness - cutoff, 3),
                "status": record.get("status"),
                "thickness_ratio": record.get("thickness_ratio"),
            }
        )
    matches.sort(key=lambda item: (item["measured_thickness_um"], str(item["strut_id"])))
    return {
        "cutoff_um": round(cutoff, 3),
        "total_below_cutoff": len(matches),
        "returned_count": min(len(matches), limit),
        "truncated": len(matches) > limit,
        "struts": matches[:limit],
    }


def build_thickness_map(struts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return compact registered endpoints for browser-side thickness coloring."""

    elements: list[dict[str, Any]] = []
    for record in struts:
        polyline = np.asarray(record.get("polyline", []), dtype=float)
        if (
            polyline.ndim != 2
            or polyline.shape[1:] != (3,)
            or len(polyline) < 2
            or not np.all(np.isfinite(polyline))
        ):
            continue
        thickness = _valid_thickness(record)
        elements.append(
            {
                "strut_id": record.get("id"),
                "start_xyz": [round(float(value), 3) for value in polyline[0]],
                "end_xyz": [round(float(value), 3) for value in polyline[-1]],
                "measured_thickness_um": (
                    round(thickness, 3) if thickness is not None else None
                ),
                "status": record.get("status"),
            }
        )
    return {
        "coordinate_space": "registered_voxel_xyz",
        "projection": "interactive_orthographic",
        "element_count": len(elements),
        "elements": elements,
    }


def compute_relative_density(
    *,
    segmented_voxel_count: int,
    enclosing_voxel_count: int,
    effective_voxel_size_mm: float,
    target_percent: float = 10.0,
    roi_definition: str,
    roi_bounds_xyz: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    """Compute segmented material volume divided by a defined enclosing ROI."""

    if segmented_voxel_count < 0:
        raise ValueError("segmented_voxel_count must be non-negative")
    if enclosing_voxel_count <= 0:
        raise ValueError("enclosing_voxel_count must be greater than zero")
    if segmented_voxel_count > enclosing_voxel_count:
        raise ValueError("segmented_voxel_count cannot exceed enclosing_voxel_count")
    voxel_size = _positive_number(effective_voxel_size_mm, "effective_voxel_size_mm")
    target = _positive_number(target_percent, "target_percent")
    voxel_volume = voxel_size**3
    segmented_volume = segmented_voxel_count * voxel_volume
    enclosing_volume = enclosing_voxel_count * voxel_volume
    density = 100.0 * segmented_voxel_count / enclosing_voxel_count
    return {
        "unit": "percent",
        "method": "segmented_material_volume_over_registered_roi_volume",
        "method_version": MEASUREMENT_METHOD_VERSION,
        "roi_definition": roi_definition,
        "roi_bounds_xyz": {
            "min_xyz": [round(float(value), 3) for value in roi_bounds_xyz["min_xyz"]],
            "max_xyz": [round(float(value), 3) for value in roi_bounds_xyz["max_xyz"]],
        },
        "effective_voxel_size_mm": round(voxel_size, 9),
        "segmented_voxel_count": int(segmented_voxel_count),
        "enclosing_voxel_count": int(enclosing_voxel_count),
        "segmented_volume_mm3": round(segmented_volume, 6),
        "enclosing_volume_mm3": round(enclosing_volume, 6),
        "relative_density_percent": round(density, 3),
        "target_percent": round(target, 3),
        "difference_percentage_points": round(density - target, 3),
    }


def default_measurement_policy(
    *,
    target_thickness_um: float = 350.0,
    critical_cutoff_um: float = 300.0,
    target_density_percent: float = 10.0,
) -> dict[str, Any]:
    """Return an explicit provisional policy used only for comparison styling."""

    target_thickness = _positive_number(target_thickness_um, "target_thickness_um")
    critical = _positive_number(critical_cutoff_um, "critical_cutoff_um")
    target_density = _positive_number(target_density_percent, "target_density_percent")
    return {
        "version": DEFAULT_POLICY_VERSION,
        "provisional": True,
        "approval_state": "demo_not_scientist_approved",
        "thickness": {
            "target_um": target_thickness,
            "critical_cutoff_um": critical,
            "pass_median_relative_band": 0.10,
            "warn_median_relative_band": 0.20,
            "pass_max_percent_below_critical": 5.0,
            "warn_max_percent_below_critical": 15.0,
        },
        "relative_density": {
            "target_percent": target_density,
            "pass_absolute_tolerance_points": 1.0,
            "warn_absolute_tolerance_points": 2.0,
        },
    }


def compare_measurements_to_policy(
    thickness: Mapping[str, Any],
    relative_density: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a versioned, transparent comparison policy to measured values."""

    active = dict(policy or default_measurement_policy(
        target_thickness_um=float(thickness["target_um"]),
        critical_cutoff_um=float(thickness["critical_cutoff_um"]),
        target_density_percent=float(relative_density["target_percent"]),
    ))
    thickness_policy = active["thickness"]
    density_policy = active["relative_density"]

    median = float(thickness["median_um"])
    target = float(thickness_policy["target_um"])
    critical_percent = float(thickness["below_critical"]["percent"])
    relative_error = abs(median - target) / target
    if (
        relative_error <= float(thickness_policy["pass_median_relative_band"])
        and critical_percent
        <= float(thickness_policy["pass_max_percent_below_critical"])
    ):
        thickness_status = "pass"
    elif (
        relative_error <= float(thickness_policy["warn_median_relative_band"])
        and critical_percent
        <= float(thickness_policy["warn_max_percent_below_critical"])
    ):
        thickness_status = "warn"
    else:
        thickness_status = "fail"

    density_value = float(relative_density["relative_density_percent"])
    density_target = float(density_policy["target_percent"])
    density_delta = abs(density_value - density_target)
    if density_delta <= float(density_policy["pass_absolute_tolerance_points"]):
        density_status = "pass"
    elif density_delta <= float(density_policy["warn_absolute_tolerance_points"]):
        density_status = "warn"
    else:
        density_status = "fail"

    order = {"pass": 0, "warn": 1, "fail": 2}
    overall = max((thickness_status, density_status), key=order.__getitem__)
    return {
        "policy": active,
        "thickness_status": thickness_status,
        "relative_density_status": density_status,
        "overall_status": overall,
        "reasons": [
            (
                f"Thickness median is {median:.3f} um and "
                f"{critical_percent:.3f}% of eligible struts are below "
                f"{float(thickness_policy['critical_cutoff_um']):.3f} um."
            ),
            (
                f"Relative density is {density_value:.3f}% versus the "
                f"{density_target:.3f}% target."
            ),
        ],
        "warning": (
            "Pass/warn/fail uses a provisional demo policy and is not an approved "
            "acceptance decision."
        ),
    }


def compute_cutoff_sensitivity(
    struts: Iterable[Mapping[str, Any]],
    cutoffs_um: Sequence[float],
) -> dict[str, Any]:
    """Compare the same measured distribution across user-selected cutoffs."""

    records = list(struts)
    values = np.asarray(
        [value for record in records if (value := _valid_thickness(record)) is not None],
        dtype=float,
    )
    if values.size == 0:
        raise ValueError("No eligible thickness values are available")
    if not cutoffs_um or len(cutoffs_um) > 20:
        raise ValueError("Provide between 1 and 20 cutoff values")
    results = []
    for raw_cutoff in cutoffs_um:
        cutoff = _positive_number(raw_cutoff, "cutoff")
        count = int(np.count_nonzero(values < cutoff))
        results.append(
            {
                "cutoff_um": round(cutoff, 3),
                "count_below": count,
                "percent_below": round(100.0 * count / values.size, 3),
            }
        )
    return {
        "eligible_strut_count": int(values.size),
        "comparison_type": "cutoff_sensitivity_no_ct_reanalysis",
        "results": results,
    }


__all__ = [
    "MEASUREMENT_METHOD_VERSION",
    "DEFAULT_POLICY_VERSION",
    "build_thickness_map",
    "compare_measurements_to_policy",
    "compute_cutoff_sensitivity",
    "compute_relative_density",
    "compute_thickness_histogram",
    "compute_thickness_summary",
    "default_measurement_policy",
    "list_out_of_spec_struts",
]
