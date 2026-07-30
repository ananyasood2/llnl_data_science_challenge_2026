from __future__ import annotations

import pytest

from lattice_pipeline.measurements import (
    build_thickness_map,
    compare_measurements_to_policy,
    compute_cutoff_sensitivity,
    compute_relative_density,
    compute_thickness_summary,
    list_out_of_spec_struts,
)


def _struts():
    return [
        {
            "id": 1,
            "status": "thin",
            "measured_thickness_um": 280.0,
            "thickness_ratio": 0.8,
            "polyline": [[0, 0, 0], [1, 1, 1]],
        },
        {
            "id": 2,
            "status": "healthy",
            "measured_thickness_um": 350.0,
            "thickness_ratio": 1.0,
            "polyline": [[1, 1, 1], [2, 2, 2]],
        },
        {
            "id": 3,
            "status": "thick",
            "measured_thickness_um": 420.0,
            "thickness_ratio": 1.2,
            "polyline": [[2, 2, 2], [3, 3, 3]],
        },
        {
            "id": 4,
            "status": "missing",
            "measured_thickness_um": None,
            "polyline": [[3, 3, 3], [4, 4, 4]],
        },
    ]


def test_thickness_summary_reports_statistics_and_exclusions() -> None:
    result = compute_thickness_summary(_struts(), user_cutoff_um=360)

    assert result["eligible_strut_count"] == 3
    assert result["excluded_strut_count"] == 1
    assert result["mean_um"] == 350.0
    assert result["median_um"] == 350.0
    assert result["min_um"] == 280.0
    assert result["max_um"] == 420.0
    assert result["below_target"] == {"cutoff_um": 350.0, "count": 1, "percent": 33.333}
    assert result["below_critical"]["count"] == 1
    assert result["below_user_cutoff"]["count"] == 2
    assert sum(item["count"] for item in result["histogram"]["bins"]) == 3


def test_invalid_or_missing_thickness_values_are_not_treated_as_zero() -> None:
    with pytest.raises(ValueError, match="No struts"):
        compute_thickness_summary(
            [{"id": 1, "measured_thickness_um": None}, {"id": 2, "measured_thickness_um": 0}]
        )


def test_outliers_are_bounded_and_ranked() -> None:
    result = list_out_of_spec_struts(_struts(), cutoff_um=360, limit=1)

    assert result["total_below_cutoff"] == 2
    assert result["truncated"] is True
    assert result["struts"][0]["strut_id"] == 1


def test_relative_density_uses_voxel_ratio_and_physical_volumes() -> None:
    result = compute_relative_density(
        segmented_voxel_count=100,
        enclosing_voxel_count=1000,
        effective_voxel_size_mm=0.1,
        target_percent=10,
        roi_definition="registered_graph_aabb",
        roi_bounds_xyz={"min_xyz": [0, 0, 0], "max_xyz": [10, 10, 10]},
    )

    assert result["segmented_volume_mm3"] == pytest.approx(0.1)
    assert result["enclosing_volume_mm3"] == pytest.approx(1.0)
    assert result["relative_density_percent"] == 10.0


def test_policy_is_explicitly_provisional_and_returns_worst_status() -> None:
    thickness = compute_thickness_summary(_struts())
    density = compute_relative_density(
        segmented_voxel_count=130,
        enclosing_voxel_count=1000,
        effective_voxel_size_mm=0.1,
        target_percent=10,
        roi_definition="registered_graph_aabb",
        roi_bounds_xyz={"min_xyz": [0, 0, 0], "max_xyz": [10, 10, 10]},
    )
    result = compare_measurements_to_policy(thickness, density)

    assert result["policy"]["provisional"] is True
    assert result["overall_status"] == "fail"
    assert "not an approved" in result["warning"]


def test_cutoff_sensitivity_and_map_are_compact_and_deterministic() -> None:
    sensitivity = compute_cutoff_sensitivity(_struts(), [300, 350, 400])
    thickness_map = build_thickness_map(_struts())

    assert [item["count_below"] for item in sensitivity["results"]] == [1, 1, 2]
    assert thickness_map["element_count"] == 4
    assert thickness_map["elements"][0]["start_xyz"] == [0.0, 0.0, 0.0]
