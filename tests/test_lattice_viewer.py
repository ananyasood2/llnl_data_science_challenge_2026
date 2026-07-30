import numpy as np

import app.app as dashboard
from app.app import (
    _clicked_element,
    _evidence_details,
    _evidence_focus,
    _inspection_figure,
    _model_performance,
    _nearest_element,
    _polyline_plane_intersections,
    _record_intersects_axis_limits,
    _rule_strength,
    _rule_strength_text,
    _selected_element,
    _selection_details,
    _strut_cross_section,
    _strut_geometry,
    _visible_summary,
)


def _analysis_fixture():
    statuses = (
        "healthy",
        "thin",
        "thick",
        "missing",
        "disconnected",
    )
    return {
        "meta": {"cache_fingerprint": "test-fixture", "threshold": 0.5},
        "struts": [
            {
                "id": index,
                "status": status,
                "rule_strength": None if status == "healthy" else 0.9,
                "component_id": 2 if status == "disconnected" else 1,
                "connectivity_reason": (
                    "secondary_skeleton_component"
                    if status == "disconnected"
                    else None
                ),
                "polyline": [[index, 0, 0], [index, 1, 1]],
            }
            for index, status in enumerate(statuses)
        ],
        "nodes": [
            {
                "id": 10,
                "status": "healthy",
                "rule_strength": None,
                "x": 0,
                "y": 0,
                "z": 0,
            },
            {
                "id": 11,
                "status": "missing",
                "rule_strength": 0.95,
                "x": 1,
                "y": 1,
                "z": 1,
            },
        ],
    }


def _component_text(component):
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, (list, tuple)):
        return " ".join(_component_text(child) for child in component)
    return _component_text(getattr(component, "children", None))


def test_requested_statuses_render_as_full_struts_and_nodes():
    figure = _inspection_figure(
        "missing_struts",
        _analysis_fixture(),
        ["healthy", "thin", "thick", "missing", "disconnected"],
        ["struts", "nodes"],
        False,
        None,
    )

    names = {trace.name for trace in figure.data}
    assert names == {
        "Healthy struts",
        "Healthy nodes",
        "Thin struts",
        "Thick struts",
        "Missing struts",
        "Missing nodes",
        "Broken / disconnected struts",
    }
    missing_strut = next(trace for trace in figure.data if trace.name == "Missing struts")
    assert missing_strut.mode == "lines"
    assert missing_strut.line.dash == "dot"
    disconnected_strut = next(
        trace
        for trace in figure.data
        if trace.name == "Broken / disconnected struts"
    )
    assert disconnected_strut.line.dash == "longdash"


def test_status_and_element_filters_are_independent():
    figure = _inspection_figure(
        "missing_struts",
        _analysis_fixture(),
        ["missing"],
        ["nodes"],
        False,
        None,
    )
    assert [trace.name for trace in figure.data] == ["Missing nodes"]


def test_click_data_resolves_the_selected_design_element():
    selected = _clicked_element(
        _analysis_fixture(),
        {"points": [{"customdata": ["strut", 3, "missing", 0.9]}]},
    )
    assert selected is not None
    assert selected[0] == "strut"
    assert selected[1]["status"] == "missing"


def test_compact_selection_resolves_against_current_analysis():
    selected = _selected_element(
        _analysis_fixture(),
        {"kind": "node", "id": 11},
    )

    assert selected is not None
    assert selected[0] == "node"
    assert selected[1]["status"] == "missing"


def test_position_resolves_to_nearest_requested_element():
    selected, distance = _nearest_element(
        _analysis_fixture(),
        "strut",
        [2.1, 0.5, 0.5],
    )

    assert selected[0] == "strut"
    assert selected[1]["id"] == 2
    assert np.isclose(distance, 0.1)


def test_evidence_focus_prefers_detector_location():
    analysis = _analysis_fixture()
    analysis["defects"] = [
        {
            "affected_element": {"kind": "strut", "id": 3},
            "location_voxel": [3.0, 0.25, 0.25],
        }
    ]

    focus = _evidence_focus(analysis, ("strut", analysis["struts"][3]))

    np.testing.assert_allclose(focus, [3.0, 0.25, 0.25])


def test_strut_geometry_reports_path_midpoint_endpoints_and_length():
    geometry = _strut_geometry(
        {
            "id": 7,
            "polyline": [[0, 0, 0], [2, 0, 0], [2, 2, 0]],
        }
    )

    np.testing.assert_allclose(geometry["start"], [0, 0, 0])
    np.testing.assert_allclose(geometry["end"], [2, 2, 0])
    np.testing.assert_allclose(geometry["midpoint"], [2, 0, 0])
    assert geometry["length"] == 4.0


def test_hover_data_includes_node_and_strut_positions():
    figure = _inspection_figure(
        "missing_struts",
        _analysis_fixture(),
        ["healthy"],
        ["struts", "nodes"],
        False,
        None,
    )

    strut_trace = next(trace for trace in figure.data if trace.name == "Healthy struts")
    node_trace = next(trace for trace in figure.data if trace.name == "Healthy nodes")
    assert "midpoint XYZ" in strut_trace.hovertemplate
    assert "length" in strut_trace.hovertemplate
    assert strut_trace.customdata[0][3] == "no defect rule triggered"
    np.testing.assert_allclose(strut_trace.customdata[0][4:7], [0, 0.5, 0.5])
    assert "XYZ" in node_trace.hovertemplate
    np.testing.assert_allclose(node_trace.customdata[0][4:7], [0, 0, 0])


def test_selection_details_include_node_and_strut_positions():
    analysis = _analysis_fixture()

    strut_details = _selection_details(("strut", analysis["struts"][0]))
    strut_text = [component.children for component in strut_details]
    assert "midpoint XYZ (0.00, 0.50, 0.50) voxels" in strut_text
    assert "start XYZ (0.00, 0.00, 0.00)" in strut_text
    assert "end XYZ (0.00, 1.00, 1.00)" in strut_text
    assert "length 1.41 voxels" in strut_text

    node_details = _selection_details(("node", analysis["nodes"][1]))
    node_text = [component.children for component in node_details]
    assert "XYZ (1.00, 1.00, 1.00) voxels" in node_text
    assert "rule strength 0.95" in node_text


def test_healthy_rule_strength_is_not_presented_as_certainty():
    healthy = {"status": "healthy", "rule_strength": None, "confidence": 1.0}
    missing = {"status": "missing", "rule_strength": 0.88}

    assert _rule_strength(healthy) is None
    assert _rule_strength_text(healthy) == "no defect rule triggered"
    assert _rule_strength_text(missing) == "rule strength 0.88"


def test_expected_strut_intersection_is_separate_from_3d_projection():
    points = np.asarray([[0, 0, 0], [10, 10, 10]], dtype=float)

    intersection = _polyline_plane_intersections(
        points,
        fixed_axis=2,
        fixed_value=5,
        horizontal_axis=0,
        vertical_axis=1,
    )

    np.testing.assert_allclose(intersection, [[5, 5]])


def test_strut_cross_section_is_centered_on_selected_3d_point():
    volume = np.zeros((11, 11, 11), dtype=float)
    volume[5, 5, 5] = 7.0
    item = {"id": 3, "polyline": [[1, 5, 5], [9, 5, 5]]}

    image, offsets = _strut_cross_section(
        volume,
        item,
        np.asarray([5, 5, 5], dtype=float),
        radius_voxels=2,
    )

    assert image.shape == (5, 5)
    np.testing.assert_allclose(offsets, [-2, -1, 0, 1, 2])
    assert image[2, 2] == 7.0


def test_evidence_details_call_score_rule_strength_and_require_review():
    analysis = _analysis_fixture()
    item = analysis["struts"][2]
    item.update(
        {
            "present_fraction": 1.0,
            "mask_material_fraction": 0.9,
            "skeleton_support_fraction": 0.8,
            "measured_thickness_um": 500.0,
            "design_thickness_um": 350.0,
            "thickness_ratio": 1.4286,
            "decision_thresholds": {"thick_ratio": 1.25},
        }
    )

    text = [
        component.children
        for component in _evidence_details(analysis, ("strut", item))
    ]

    assert "Needs review" in text
    assert "rule strength 0.90" in text
    assert "thickness ratio 1.43×" in text
    assert "thick rule > 1.25×" in text


def test_manual_y_axis_maximum_is_applied_to_the_scene():
    figure = _inspection_figure(
        "missing_struts",
        _analysis_fixture(),
        ["healthy"],
        ["struts"],
        False,
        None,
        "XYZ",
        {"X": None, "Y": 10, "Z": None},
    )

    assert figure.layout.scene.xaxis.range is None
    assert tuple(figure.layout.scene.yaxis.range) == (0.0, 10.0)
    assert figure.layout.scene.zaxis.range is None


def test_axis_maximum_filters_rendered_elements_and_missing_counts():
    analysis = _analysis_fixture()
    axis_maxima = {"X": 2, "Y": None, "Z": None}
    figure = _inspection_figure(
        "missing_struts",
        analysis,
        ["healthy", "thin", "thick", "missing", "disconnected"],
        ["struts", "nodes"],
        False,
        None,
        "XYZ",
        axis_maxima,
    )
    summary = _visible_summary(
        analysis,
        ["healthy", "thin", "thick", "missing", "disconnected"],
        ["struts", "nodes"],
        axis_maxima,
    )

    assert "Missing struts" not in {trace.name for trace in figure.data}
    assert summary[0].children == "3 struts · 2 nodes visible"
    assert summary[2].children == "0 missing struts · 1 missing nodes detected"
    assert summary[4].children == (
        "0 broken / disconnected struts · 0 broken / disconnected nodes"
    )
    assert summary[6].children == (
        "0 boundary / uncertain struts · 0 boundary / uncertain nodes"
    )
    assert summary[8].children == "1 thin struts · 0 thin nodes"
    assert summary[10].children == "1 thick struts · 0 thick nodes"
    assert summary[12].children == "1 healthy struts · 1 healthy nodes"
    assert summary[14].children == "3 total flagged elements"


def test_summary_counts_all_statuses_even_when_a_status_is_filtered_out():
    analysis = _analysis_fixture()
    analysis["struts"][0]["status"] = "uncertain"

    summary = _visible_summary(
        analysis,
        ["missing"],
        ["struts"],
    )

    assert summary[0].children == "1 struts · 0 nodes visible"
    assert summary[2].children == "1 missing struts · 1 missing nodes detected"
    assert summary[4].children == (
        "1 broken / disconnected struts · 0 broken / disconnected nodes"
    )
    assert summary[6].children == (
        "1 boundary / uncertain struts · 0 boundary / uncertain nodes"
    )
    assert summary[8].children == "1 thin struts · 0 thin nodes"
    assert summary[10].children == "1 thick struts · 0 thick nodes"
    assert summary[12].children == "0 healthy struts · 1 healthy nodes"
    assert summary[14].children == "6 total flagged elements"


def test_disconnected_strut_evidence_identifies_secondary_component():
    analysis = _analysis_fixture()
    item = analysis["struts"][4]

    details = _evidence_details(analysis, ("strut", item))
    text = _component_text(details)

    assert "Broken / disconnected candidate" in text
    assert "skeleton component 2" in text
    assert "separate from the main lattice network" in text


def test_ct_reading_explains_missing_strut_from_measured_support():
    analysis = _analysis_fixture()
    item = analysis["struts"][3]
    item.update(
        {
            "present_fraction": 0.08,
            "mask_material_fraction": 0.05,
            "skeleton_support_fraction": 0.04,
            "decision_thresholds": {"missing_present_fraction": 0.15},
        }
    )

    text = _component_text(_evidence_details(analysis, ("strut", item)))

    assert "What the CT scan shows for this strut" in text
    assert "8.0% path support" in text
    assert "below the 15.0% missing-material cutoff" in text


def test_whole_model_performance_panel_formats_all_four_percentages():
    analysis = {
        "validation": {
            "overall": {
                "accuracy": 0.98,
                "precision": 0.8,
                "recall": 0.75,
                "f1": 0.7742,
                "true_positive": 6,
                "true_negative": 92,
                "false_positive": 1,
                "false_negative": 2,
                "total": 101,
            }
        }
    }

    panel = _model_performance(analysis)
    text = _component_text(panel)

    assert "Accuracy" in text and "98.0%" in text
    assert "Precision" in text and "80.0%" in text
    assert "Recall" in text and "75.0%" in text
    assert "F1" in text and "77.4%" in text
    assert "101 validated elements" in text
    assert "Missing / disconnected detection performance" in text
    assert "Both missing and broken / disconnected detector labels" in text


def test_model_performance_panel_calculates_live_3d_defect_percentages():
    analysis = _analysis_fixture()

    panel = _model_performance(analysis)
    text = _component_text(panel)

    assert "LIVE 3D MODEL" in text
    assert "Missing / disconnected percentage" in text
    assert "Struts 40.00% 2 of 5" in text
    assert "Nodes 50.00% 1 of 2" in text
    assert "Combined 42.86% 3 of 7" in text
    assert "1 missing + 1 disconnected struts" in text
    assert "1 missing + 0 disconnected nodes" in text
    assert "CAD validation unavailable" in text


def test_strut_crossing_axis_limit_is_still_in_the_displayed_region():
    strut = {
        "id": 99,
        "polyline": [[-1, 1, 1], [3, 1, 1]],
    }

    assert _record_intersects_axis_limits(
        strut,
        "strut",
        {"X": 2, "Y": 2, "Z": 2},
    )


def test_embedded_threshold_geometry_avoids_reloading_current_mask(monkeypatch):
    analysis = _analysis_fixture()
    analysis["_display_geometry"] = {
        "surface_vertices_xyz": np.asarray(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            dtype=float,
        ),
        "surface_faces": np.asarray([[0, 1, 2]], dtype=int),
    }

    def fail_if_reloaded(*_args):
        raise AssertionError("cached threshold geometry should be reused")

    monkeypatch.setattr(dashboard, "_display_geometry", fail_if_reloaded)
    figure = _inspection_figure(
        "missing_struts",
        analysis,
        ["healthy"],
        ["struts"],
        True,
        None,
    )

    assert figure.data[0].name == "CT segmentation"


def test_boundary_uncertain_strut_has_distinct_trace_style():
    analysis = _analysis_fixture()
    analysis["struts"][0]["status"] = "uncertain"

    figure = _inspection_figure(
        "missing_struts",
        analysis,
        ["uncertain"],
        ["struts"],
        False,
        None,
    )

    assert figure.data[0].name == "Boundary / uncertain struts"
    assert figure.data[0].line.dash == "dash"
