import numpy as np

import app.app as dashboard
from app.app import (
    _clicked_element,
    _inspection_figure,
    _record_intersects_axis_limits,
    _visible_summary,
)


def _analysis_fixture():
    statuses = ("healthy", "thin", "thick", "missing")
    return {
        "meta": {"cache_fingerprint": "test-fixture"},
        "struts": [
            {
                "id": index,
                "status": status,
                "confidence": 0.9,
                "polyline": [[index, 0, 0], [index, 1, 1]],
            }
            for index, status in enumerate(statuses)
        ],
        "nodes": [
            {
                "id": 10,
                "status": "healthy",
                "confidence": 1.0,
                "x": 0,
                "y": 0,
                "z": 0,
            },
            {
                "id": 11,
                "status": "missing",
                "confidence": 0.95,
                "x": 1,
                "y": 1,
                "z": 1,
            },
        ],
    }


def test_requested_statuses_render_as_full_struts_and_nodes():
    figure = _inspection_figure(
        "missing_struts",
        _analysis_fixture(),
        ["healthy", "thin", "thick", "missing"],
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
    }
    missing_strut = next(trace for trace in figure.data if trace.name == "Missing struts")
    assert missing_strut.mode == "lines"
    assert missing_strut.line.dash == "dot"


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
        ["healthy", "thin", "thick", "missing"],
        ["struts", "nodes"],
        False,
        None,
        "XYZ",
        axis_maxima,
    )
    summary = _visible_summary(
        analysis,
        ["healthy", "thin", "thick", "missing"],
        ["struts", "nodes"],
        axis_maxima,
    )

    assert "Missing struts" not in {trace.name for trace in figure.data}
    assert summary[0].children == "3 struts · 2 nodes visible"
    assert summary[2].children == "0 missing struts · 1 missing nodes detected"


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
