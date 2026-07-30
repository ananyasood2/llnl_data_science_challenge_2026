"""Regression tests for bounded, deterministic copilot tool outputs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.copilot.contracts import ViewportContextCreate
from app.copilot.orchestrator import _tool_plan
from app.copilot.repository import analysis_repository
from app.copilot.store import ViewportContextStore, viewport_context_store
from app.copilot.tools import (
    analyze_connectivity_in_bounds,
    identify_disconnected_components,
    inspect_selected_element,
    list_visible_elements,
    summarize_visible_defects,
)


@pytest.fixture()
def copilot_context(monkeypatch: pytest.MonkeyPatch):
    analysis = {
        "meta": {"cache_fingerprint": "analysis-fingerprint"},
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0, "status": "healthy", "component_id": 1},
            {"id": 2, "x": 5.0, "y": 0.0, "z": 0.0, "status": "healthy", "component_id": 1},
            {"id": 3, "x": 10.0, "y": 0.0, "z": 0.0, "status": "missing", "component_id": 2},
        ],
        "struts": [
            {
                "id": 10,
                "node_a": 1,
                "node_b": 2,
                "polyline": [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]],
                "status": "healthy",
                "component_id": 1,
                "present_fraction": 1.0,
                "skeleton_support_fraction": 1.0,
            },
            {
                "id": 11,
                "node_a": 2,
                "node_b": 3,
                "polyline": [[5.0, 0.0, 0.0], [10.0, 0.0, 0.0]],
                "status": "missing",
                "component_id": 2,
                "present_fraction": 0.1,
                "skeleton_support_fraction": 0.0,
                "rule_strength": 0.88,
                "decision_thresholds": {"missing_present_fraction": 0.22},
            },
        ],
        "components": [
            {"id": 1, "is_main": True, "n_skeleton_voxels": 100},
            {"id": 2, "is_main": False, "n_skeleton_voxels": 12},
        ],
    }
    monkeypatch.setattr(analysis_repository, "supports", lambda dataset_id: dataset_id == "missing_struts")
    monkeypatch.setattr(analysis_repository, "get_analysis", lambda dataset_id, threshold: analysis)
    payload = ViewportContextCreate.model_validate(
        {
            "captured_at": datetime.now(UTC).isoformat(),
            "dataset_id": "missing_struts",
            "threshold": {"value": 0.4, "source": "manual"},
            "region": {"min_xyz": [0, 0, 0], "max_xyz": [12, 2, 2]},
            "camera": {"eye": {"x": 1, "y": 1, "z": 1}},
            "visible_statuses": ["healthy", "missing"],
            "visible_element_types": ["strut", "node"],
            "selected_element": {"kind": "strut", "id": 11},
            "viewer_revision": 3,
        }
    )
    return viewport_context_store.put(payload, {"graph_hash": "graph", "artifact_revision": "artifact"})


def test_connectivity_is_scoped_and_compact(copilot_context) -> None:
    result = analyze_connectivity_in_bounds(copilot_context.context_id)

    assert result["tool_name"] == "analyze_connectivity_in_bounds"
    assert result["summary"]["visible_strut_count"] == 2
    assert result["summary"]["disconnected_visible_strut_count"] == 1
    assert "active filters" in result["warnings"][0]
    assert "polyline" not in str(result)


def test_visible_elements_paginates_and_selected_inspection_keeps_rule_inputs(copilot_context) -> None:
    listing = list_visible_elements(copilot_context.context_id, ["strut"], limit=1)
    inspection = inspect_selected_element(copilot_context.context_id)

    assert listing["summary"]["next_cursor"] == 1
    assert len(listing["elements"]) == 1
    assert inspection["summary"]["selected"]["id"] == 11
    assert inspection["summary"]["selected"]["decision_thresholds"]["missing_present_fraction"] == 0.22


def test_disconnected_and_defect_tools_return_only_current_scope(copilot_context) -> None:
    components = identify_disconnected_components(copilot_context.context_id)
    defects = summarize_visible_defects(copilot_context.context_id)

    assert components["summary"]["disconnected_component_count"] == 1
    assert components["elements"][0]["visible_strut_ids"] == [11]
    assert defects["summary"]["status_counts"] == {"healthy": 3, "missing": 2}


def test_context_is_available_to_a_separate_mcp_process_store(copilot_context) -> None:
    reloaded_store = ViewportContextStore()

    restored = reloaded_store.get(copilot_context.context_id)

    assert restored.fingerprint == copilot_context.fingerprint


def test_full_selected_element_review_uses_evidence_backed_tools() -> None:
    tool_names = [name for name, _tool in _tool_plan("Perform a full selected-element evidence review.")]

    assert tool_names == [
        "inspect_selected_element",
        "compare_expected_geometry_with_ct",
        "generate_ct_evidence_slices",
    ]
