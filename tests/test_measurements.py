from __future__ import annotations

import pytest

from lattice_pipeline.measurements import (
    build_thickness_map,
    compare_measurements_to_policy,
    compute_cutoff_sensitivity,
    compute_relative_density,
    compute_thickness_summary,
    inspect_strut_measurement,
    list_out_of_spec_struts,
)


def _struts():
    return [
        {
            "id": 1,
            "status": "thin",
            "measured_thickness_um": 280.0,
            "design_thickness_um": 350.0,
            "thickness_ratio": 0.8,
            "node_a": 0,
            "node_b": 1,
            "polyline": [[0, 0, 0], [1, 1, 1]],
        },
        {
            "id": 2,
            "status": "healthy",
            "measured_thickness_um": 350.0,
            "design_thickness_um": 350.0,
            "thickness_ratio": 1.0,
            "node_a": 1,
            "node_b": 2,
            "polyline": [[1, 1, 1], [2, 2, 2]],
        },
        {
            "id": 3,
            "status": "thick",
            "measured_thickness_um": 420.0,
            "design_thickness_um": 350.0,
            "thickness_ratio": 1.2,
            "node_a": 2,
            "node_b": 3,
            "polyline": [[2, 2, 2], [3, 3, 3]],
        },
        {
            "id": 4,
            "status": "missing",
            "measured_thickness_um": None,
            "design_thickness_um": 350.0,
            "node_a": 3,
            "node_b": 4,
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


def test_selected_strut_uses_weak_ecdf_strict_cutoffs_and_endpoint_neighbors() -> None:
    result = inspect_strut_measurement(
        _struts(),
        "2",
        target_um=350,
        critical_cutoff_um=300,
        user_cutoff_um=360,
    )

    selected = result["strut"]
    assert selected["strut_id"] == 2
    assert selected["measurement_eligible"] is True
    assert selected["percentile"] == {
        "rank_percent": 66.667,
        "count_at_or_below": 2,
        "population_count": 3,
        "method": "weak_ecdf_lte",
    }
    assert selected["target_comparison"] == {
        "target_um": 350.0,
        "difference_um": 0.0,
        "below": False,
    }
    assert selected["user_cutoff_comparison"]["below"] is True
    assert result["neighbors"]["total_count"] == 2
    assert result["neighbors"]["eligible_count"] == 2
    assert result["neighbors"]["median_thickness_um"] == 350.0
    assert result["neighbors"]["selected_minus_median_um"] == 0.0
    assert [item["strut_id"] for item in result["neighbors"]["struts"]] == [1, 3]


def test_unmeasured_selected_strut_retains_status_and_null_comparisons() -> None:
    result = inspect_strut_measurement(_struts(), 4)

    selected = result["strut"]
    assert selected["analysis_status"] == "missing"
    assert selected["measurement_eligible"] is False
    assert selected["percentile"]["rank_percent"] is None
    assert selected["percentile"]["count_at_or_below"] is None
    assert selected["target_comparison"]["difference_um"] is None
    assert selected["target_comparison"]["below"] is None
    assert result["neighbors"]["selected_minus_median_um"] is None
    assert any("no finite positive" in warning for warning in result["warnings"])


def test_selected_strut_weak_ecdf_includes_ties_and_neighbor_list_is_bounded() -> None:
    records = _struts()
    records.append(
        {
            "id": "tie",
            "status": "healthy",
            "measured_thickness_um": 350.0,
            "design_thickness_um": 350.0,
            "thickness_ratio": 1.0,
            "node_a": 1,
            "node_b": 5,
        }
    )

    result = inspect_strut_measurement(records, 2, neighbor_limit=1)

    assert result["strut"]["percentile"]["count_at_or_below"] == 3
    assert result["strut"]["percentile"]["population_count"] == 4
    assert result["strut"]["percentile"]["rank_percent"] == 75.0
    assert result["neighbors"]["total_count"] == 3
    assert result["neighbors"]["returned_count"] == 1
    assert result["neighbors"]["truncated"] is True


def test_selected_strut_identifier_prefers_exact_type_before_canonical_fallback() -> None:
    records = [
        {
            "id": 42,
            "status": "integer-id",
            "measured_thickness_um": 310.0,
            "node_a": 1,
            "node_b": 2,
        },
        {
            "id": "42",
            "status": "string-id",
            "measured_thickness_um": 390.0,
            "node_a": 3,
            "node_b": 4,
        },
    ]

    integer_result = inspect_strut_measurement(records, 42)
    string_result = inspect_strut_measurement(records, "42")

    assert integer_result["strut"]["strut_id"] == 42
    assert integer_result["strut"]["analysis_status"] == "integer-id"
    assert integer_result["strut"]["measured_thickness_um"] == 310.0
    assert string_result["strut"]["strut_id"] == "42"
    assert string_result["strut"]["analysis_status"] == "string-id"
    assert string_result["strut"]["measured_thickness_um"] == 390.0


def _topology_edge_case_struts() -> list[dict]:
    return [
        {
            "id": "selected",
            "status": "healthy",
            "measured_thickness_um": 350.0,
            "node_a": "a",
            "node_b": "b",
            "polyline": [[0, 0, 0], [1, 0, 0]],
        },
        {
            "id": "shares-both",
            "status": "thin",
            "measured_thickness_um": 300.0,
            "node_a": "a",
            "node_b": "b",
            "polyline": [[10, 10, 10], [11, 10, 10]],
        },
        {
            "id": "unmeasured-neighbor",
            "status": "missing",
            "measured_thickness_um": None,
            "node_a": "b",
            "node_b": "c",
            "polyline": [[20, 20, 20], [21, 20, 20]],
        },
        {
            "id": "geometrically-near-only",
            "status": "thin",
            "measured_thickness_um": 275.0,
            "node_a": "x",
            "node_b": "y",
            "polyline": [[0, 0, 0], [1, 0, 0]],
        },
    ]


def test_neighbor_sharing_both_endpoints_is_returned_once() -> None:
    result = inspect_strut_measurement(_topology_edge_case_struts(), "selected")

    matching = [
        item
        for item in result["neighbors"]["struts"]
        if item["strut_id"] == "shares-both"
    ]
    assert len(matching) == 1
    assert matching[0]["shared_node_ids"] == ["a", "b"]


def test_geometrically_near_strut_without_shared_node_is_not_a_neighbor() -> None:
    result = inspect_strut_measurement(_topology_edge_case_struts(), "selected")

    neighbor_ids = {item["strut_id"] for item in result["neighbors"]["struts"]}
    assert "geometrically-near-only" not in neighbor_ids
    assert result["neighbors"]["total_count"] == 2


def test_unmeasured_neighbor_is_counted_but_excluded_from_median() -> None:
    result = inspect_strut_measurement(_topology_edge_case_struts(), "selected")

    assert result["neighbors"]["total_count"] == 2
    assert result["neighbors"]["eligible_count"] == 1
    assert result["neighbors"]["excluded_count"] == 1
    assert result["neighbors"]["median_thickness_um"] == 300.0
    assert result["neighbors"]["selected_minus_median_um"] == 50.0
    unmeasured = next(
        item
        for item in result["neighbors"]["struts"]
        if item["strut_id"] == "unmeasured-neighbor"
    )
    assert unmeasured["measured_thickness_um"] is None
