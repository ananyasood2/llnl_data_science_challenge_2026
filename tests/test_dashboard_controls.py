from __future__ import annotations

import numpy as np
import pytest

import app.app as dashboard
from app.app import (
    _axis_indices,
    _display_axis_ranges,
    _evidence_deep_link_selection,
    _parse_evidence_deep_link,
    _reorder_xyz,
    _selection_reference,
    create_app,
)


def _component_ids(component: object) -> set[str]:
    identifiers: set[str] = set()
    identifier = getattr(component, "id", None)
    if identifier is not None:
        identifiers.add(identifier)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            identifiers.update(_component_ids(child))
    elif children is not None:
        identifiers.update(_component_ids(children))
    return identifiers


def test_standard_axis_order_preserves_xyz_coordinates() -> None:
    points = np.asarray([[1, 2, 3], [4, 5, 6]])
    np.testing.assert_allclose(_reorder_xyz(points, "XYZ"), points)


def test_raw_array_axis_order_maps_xyz_to_zyx() -> None:
    point = _reorder_xyz([10, 20, 30], "ZYX")
    np.testing.assert_allclose(point, [30, 20, 10])


def test_all_axis_orders_are_valid_permutations() -> None:
    for order in ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"):
        assert sorted(_axis_indices(order)) == [0, 1, 2]


def test_invalid_axis_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown axis order"):
        _reorder_xyz([1, 2, 3], "XXZ")


def test_axis_maxima_follow_semantic_axes_when_display_is_remapped() -> None:
    assert _display_axis_ranges(
        "YZX",
        {"X": 30, "Y": 10, "Z": None},
    ) == ([0.0, 10.0], None, [0.0, 30.0])


def test_axis_maxima_reject_non_positive_values() -> None:
    with pytest.raises(ValueError, match="Y-axis maximum"):
        _display_axis_ranges("XYZ", {"Y": 0})


def test_display_axis_remapping_control_is_not_in_the_dashboard() -> None:
    identifiers = _component_ids(create_app("unitcell").layout)

    assert "axis-order" not in identifiers
    assert {"x-axis-max", "y-axis-max", "z-axis-max"} <= identifiers
    assert "model-performance" in identifiers


def test_evidence_deep_link_controls_are_wired_into_dashboard() -> None:
    viewer_app = create_app("unitcell")
    identifiers = _component_ids(viewer_app.layout)
    selection_callback = next(
        callback
        for output, callback in viewer_app.callback_map.items()
        if "selected-element.data" in output
    )
    scroll_callback = next(
        callback
        for callback in viewer_app._callback_list
        if callback["output"] == "evidence-scroll-state.data"
    )

    assert {
        "viewer-location",
        "evidence-panel",
        "evidence-scroll-state",
    } <= identifiers
    assert {item["id"] for item in selection_callback["inputs"]} >= {
        "viewer-location",
        "viewer",
        "inspect-element",
    }
    assert scroll_callback["inputs"] == [
        {"id": "evidence-details", "property": "children"}
    ]
    assert {item["id"] for item in scroll_callback["state"]} == {
        "selected-element",
        "viewer-location",
        "evidence-scroll-state",
    }
    assert scroll_callback["clientside_function"] is not None
    assert "scrollIntoView" in dashboard._EVIDENCE_SCROLL_CLIENTSIDE
    assert 'selected.source !== "evidence-deep-link"' in (
        dashboard._EVIDENCE_SCROLL_CLIENTSIDE
    )


def test_only_evidence_deep_links_mark_selection_for_automatic_scroll() -> None:
    selected = ("strut", {"id": 1284})

    assert _selection_reference(selected) == {"kind": "strut", "id": 1284}
    assert _selection_reference(selected, evidence_deep_link=True) == {
        "kind": "strut",
        "id": 1284,
        "source": "evidence-deep-link",
    }


def test_evidence_deep_link_parser_preserves_qualified_identifiers() -> None:
    assert _parse_evidence_deep_link("?threshold=0.42") is None
    assert _parse_evidence_deep_link(
        "?datasetId=missing_struts&analysisRevision=revision-123"
        "&elementKind=strut&elementId=1284"
    ) == {
        "datasetId": "missing_struts",
        "analysisRevision": "revision-123",
        "elementKind": "strut",
        "elementId": "1284",
    }


@pytest.mark.parametrize(
    "search, message",
    [
        ("?datasetId=missing_struts", "incomplete"),
        (
            "?datasetId=missing_struts&datasetId=unitcell"
            "&analysisRevision=revision-123&elementKind=strut&elementId=1",
            "repeated datasetId",
        ),
        (
            "?datasetId=missing_struts&analysisRevision=revision-123"
            "&elementKind=beam&elementId=1",
            "element kind",
        ),
    ],
)
def test_evidence_deep_link_parser_rejects_invalid_requests(
    search: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _parse_evidence_deep_link(search)


def test_evidence_deep_link_resolves_exact_current_revision_element() -> None:
    analysis = {
        "meta": {"cache_fingerprint": "revision-123"},
        "struts": [{"id": 1284}],
        "nodes": [{"id": "node-2"}],
    }

    selected = _evidence_deep_link_selection(
        "?datasetId=missing_struts&analysisRevision=revision-123"
        "&elementKind=strut&elementId=1284",
        "missing_struts",
        analysis,
    )

    assert selected == ("strut", analysis["struts"][0])


@pytest.mark.parametrize(
    "search, message",
    [
        (
            "?datasetId=unitcell&analysisRevision=revision-123"
            "&elementKind=strut&elementId=1284",
            "does not match this viewer",
        ),
        (
            "?datasetId=missing_struts&analysisRevision=old-revision"
            "&elementKind=strut&elementId=1284",
            "does not match the current registered analysis",
        ),
        (
            "?datasetId=missing_struts&analysisRevision=revision-123"
            "&elementKind=strut&elementId=9999",
            "No strut with ID 9999",
        ),
    ],
)
def test_evidence_deep_link_rejects_mismatch_or_unknown_element(
    search: str,
    message: str,
) -> None:
    analysis = {
        "meta": {"cache_fingerprint": "revision-123"},
        "struts": [{"id": 1284}],
        "nodes": [],
    }

    with pytest.raises(ValueError, match=message):
        _evidence_deep_link_selection(search, "missing_struts", analysis)


def test_connectivity_failures_share_one_dashboard_filter() -> None:
    options = dashboard._filter_options()

    assert [option["value"] for option in options] == [
        "missing",
        "disconnected",
        "uncertain",
        "thin",
        "thick",
        "healthy",
    ]
    connectivity = next(
        option for option in options if option["value"] == "disconnected"
    )
    assert "Broken / disconnected" in connectivity["label"].children


def test_recent_threshold_analyses_are_reused(monkeypatch) -> None:
    calls: list[float | None] = []

    def fake_analysis(
        dataset_key: str,
        config: dict,
        *,
        threshold: float | None,
        voxel_size_mm: float,
    ) -> dict:
        del config, voxel_size_mm
        calls.append(threshold)
        return {
            "meta": {
                "cache_fingerprint": f"{dataset_key}:{threshold}",
            },
        }

    monkeypatch.setattr(dashboard, "ensure_analysis", fake_analysis)
    monkeypatch.setattr(dashboard, "get_dataset", lambda _key: {})
    monkeypatch.setattr(
        dashboard,
        "_display_geometry",
        lambda _dataset, fingerprint: {"fingerprint": fingerprint},
    )
    dashboard._ANALYSES.clear()
    try:
        first = dashboard._analysis("unitcell", 0.0252, 0.1)
        dashboard._analysis("unitcell", 0.0252, 0.2)
        repeated = dashboard._analysis("unitcell", 0.0252, 0.1)
    finally:
        dashboard._ANALYSES.clear()

    assert calls == [0.1, 0.2]
    assert repeated is first
    assert repeated["_display_geometry"]["fingerprint"] == "unitcell:0.1"
