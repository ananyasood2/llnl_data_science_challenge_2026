"""Deterministic, dataset-scoped copilot tools.

These functions deliberately return compact JSON-safe summaries.  They are
shared by HTTP, MCP, and the chat orchestrator so no scientific calculation is
duplicated by an agent prompt.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
from fastapi import HTTPException

from app.core.config import get_settings

from .contracts import StoredViewportContext, ToolEnvelope
from .repository import analysis_repository
from .store import viewport_context_store

ElementKind = Literal["strut", "node"]


def _context(context_id: str) -> StoredViewportContext:
    context = viewport_context_store.get(context_id)
    if not analysis_repository.supports(context.dataset_id):
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dataset {context.dataset_id!r} is not available to the registered copilot. "
                "Use the bundled missing_struts dataset or complete uploaded-dataset registration."
            ),
        )
    return context


def _analysis(context: StoredViewportContext) -> dict[str, Any]:
    try:
        return analysis_repository.get_analysis(context.dataset_id, context.threshold.value)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _scope(context: StoredViewportContext) -> dict[str, Any]:
    return {
        "region_method": "axis_aligned_display_bounds",
        "coordinate_space": context.coordinate_space,
        "min_xyz": context.region.min_xyz,
        "max_xyz": context.region.max_xyz,
        "visible_statuses": context.visible_statuses,
        "visible_element_types": context.visible_element_types,
        "viewer_revision": context.viewer_revision,
    }


def _envelope(
    context: StoredViewportContext,
    tool_name: str,
    summary: dict[str, Any],
    *,
    elements: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return ToolEnvelope(
        tool_name=tool_name,
        context_id=context.context_id,
        dataset_id=context.dataset_id,
        analysis_revision=context.analysis_revision["artifact_revision"],
        scope=_scope(context),
        summary=summary,
        elements=elements or [],
        evidence=evidence or [],
        warnings=warnings or [],
        provenance={
            "analysis_cache_fingerprint": context.analysis_revision["artifact_revision"],
            "threshold": context.threshold.model_dump(),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    ).model_dump(mode="json")


def _record_bounds(record: dict[str, Any], kind: ElementKind) -> tuple[np.ndarray, np.ndarray]:
    if kind == "node":
        point = np.asarray([record["x"], record["y"], record["z"]], dtype=float)
        return point, point
    points = np.asarray(record["polyline"], dtype=float)
    return points.min(axis=0), points.max(axis=0)


def _intersects_context(record: dict[str, Any], kind: ElementKind, context: StoredViewportContext) -> bool:
    lower, upper = _record_bounds(record, kind)
    region_min = np.asarray(context.region.min_xyz, dtype=float)
    region_max = np.asarray(context.region.max_xyz, dtype=float)
    return bool(np.all(upper >= region_min) and np.all(lower <= region_max))


def _compact_element(record: dict[str, Any], kind: ElementKind) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": kind,
        "id": record["id"],
        "status": record.get("status"),
        "component_id": record.get("component_id"),
        "rule_strength": record.get("rule_strength", record.get("confidence")),
    }
    if kind == "node":
        base["position_xyz"] = [round(float(record[key]), 3) for key in ("x", "y", "z")]
    else:
        polyline = np.asarray(record["polyline"], dtype=float)
        base.update(
            {
                "node_a": record.get("node_a"),
                "node_b": record.get("node_b"),
                "midpoint_xyz": [round(float(value), 3) for value in polyline.mean(axis=0)],
                "present_fraction": record.get("present_fraction"),
                "skeleton_support_fraction": record.get("skeleton_support_fraction"),
                "measured_thickness_um": record.get("measured_thickness_um"),
            }
        )
    return base


def _visible_records(
    context: StoredViewportContext,
    analysis: dict[str, Any],
    kinds: Iterable[ElementKind] | None = None,
    *,
    respect_filters: bool = True,
) -> list[tuple[ElementKind, dict[str, Any]]]:
    requested = set(kinds or ("strut", "node"))
    allowed_statuses = set(context.visible_statuses)
    allowed_kinds = set(context.visible_element_types)
    visible: list[tuple[ElementKind, dict[str, Any]]] = []
    for kind, key in (("strut", "struts"), ("node", "nodes")):
        if kind not in requested or (respect_filters and kind not in allowed_kinds):
            continue
        for record in analysis[key]:
            if not _intersects_context(record, kind, context):
                continue
            if respect_filters and record.get("status") not in allowed_statuses:
                continue
            visible.append((kind, record))
    return visible


def get_current_viewport_context(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    return _envelope(
        context,
        "get_current_viewport_context",
        {
            "fingerprint": context.fingerprint,
            "captured_at": context.captured_at.isoformat(),
            "expires_at": context.expires_at.isoformat(),
            "selected_element": (
                context.selected_element.model_dump() if context.selected_element else None
            ),
            "camera": context.camera.model_dump(),
        },
    )


def list_visible_elements(
    context_id: str,
    kinds: list[ElementKind] | None = None,
    cursor: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    context = _context(context_id)
    if cursor < 0 or limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="cursor must be >= 0 and limit must be 1..200")
    records = _visible_records(context, _analysis(context), kinds)
    page = records[cursor : cursor + limit]
    return _envelope(
        context,
        "list_visible_elements",
        {
            "total_visible": len(records),
            "next_cursor": cursor + limit if cursor + limit < len(records) else None,
        },
        elements=[_compact_element(record, kind) for kind, record in page],
    )


def _induced_components(struts: list[dict[str, Any]]) -> list[list[int]]:
    parent: dict[int, int] = {}

    def find(value: int) -> int:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def join(a: int, b: int) -> None:
        a_root, b_root = find(a), find(b)
        if a_root != b_root:
            parent[b_root] = a_root

    for item in struts:
        if item.get("node_a") is not None and item.get("node_b") is not None:
            join(int(item["node_a"]), int(item["node_b"]))
    groups: dict[int, list[int]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    return sorted((sorted(nodes) for nodes in groups.values()), key=lambda nodes: (-len(nodes), nodes))


def analyze_connectivity_in_bounds(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    analysis = _analysis(context)
    visible = _visible_records(context, analysis, ["strut"])
    struts = [record for _, record in visible]
    induced = _induced_components(struts)
    ct_component_counts = Counter(
        int(record["component_id"])
        for record in struts
        if record.get("component_id") is not None
    )
    disconnected = [
        _compact_element(record, "strut")
        for record in struts
        if record.get("component_id") is not None
        and not next(
            (component.get("is_main", False) for component in analysis["components"] if component["id"] == record["component_id"]),
            False,
        )
    ]
    warning = (
        "Connectivity is scoped to displayed bounds and active filters; it is not a global lattice claim."
    )
    return _envelope(
        context,
        "analyze_connectivity_in_bounds",
        {
            "visible_strut_count": len(struts),
            "induced_design_component_count": len(induced),
            "largest_induced_component_nodes": len(induced[0]) if induced else 0,
            "ct_component_count_in_visible_struts": len(ct_component_counts),
            "ct_component_strut_counts": dict(sorted(ct_component_counts.items())),
            "disconnected_visible_strut_count": len(disconnected),
        },
        elements=disconnected[:100],
        warnings=[warning],
    )


def identify_disconnected_components(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    analysis = _analysis(context)
    visible_struts = [record for _, record in _visible_records(context, analysis, ["strut"])]
    visible_ids = {int(record["id"]) for record in visible_struts}
    component_members: dict[int, list[int]] = defaultdict(list)
    for record in visible_struts:
        if record.get("component_id") is not None:
            component_members[int(record["component_id"])].append(int(record["id"]))
    components = []
    for component in analysis.get("components", []):
        component_id = int(component["id"])
        members = component_members.get(component_id, [])
        if not members or component.get("is_main", False):
            continue
        components.append(
            {
                "component_id": component_id,
                "is_main": False,
                "n_skeleton_voxels": component.get("n_skeleton_voxels"),
                "visible_strut_ids": sorted(members)[:100],
            }
        )
    return _envelope(
        context,
        "identify_disconnected_components",
        {"disconnected_component_count": len(components), "visible_strut_count": len(visible_ids)},
        elements=components,
        warnings=["Only non-main CT components with currently visible struts are returned."],
    )


def _find_element(analysis: dict[str, Any], kind: ElementKind, element_id: int | str) -> dict[str, Any]:
    key = "struts" if kind == "strut" else "nodes"
    for record in analysis[key]:
        if str(record.get("id")) == str(element_id):
            return record
    raise HTTPException(status_code=404, detail=f"{kind.title()} ID {element_id!r} was not found.")


def inspect_selected_element(
    context_id: str,
    kind: ElementKind | None = None,
    element_id: int | str | None = None,
) -> dict[str, Any]:
    context = _context(context_id)
    selected = context.selected_element
    if kind is None or element_id is None:
        if selected is None:
            raise HTTPException(status_code=409, detail="Select a strut or node before inspecting it.")
        kind, element_id = selected.kind, selected.id
    record = _find_element(_analysis(context), kind, element_id)
    details = _compact_element(record, kind)
    details["decision_thresholds"] = record.get("decision_thresholds", {})
    details["boundary_reason"] = record.get("boundary_reason")
    details["classification_explanation"] = {
        "status": record.get("status"),
        "rule_strength": record.get("rule_strength", record.get("confidence")),
        "rule_strength_note": "Decision margin, not a calibrated probability.",
    }
    return _envelope(context, "inspect_selected_element", {"selected": details}, elements=[details])


def generate_ct_evidence_slices(context_id: str) -> dict[str, Any]:
    inspected = inspect_selected_element(context_id)
    context = _context(context_id)
    selected = inspected["summary"]["selected"]
    artifact_key = hashlib.sha256(
        f"{context.dataset_id}:{context.analysis_revision['artifact_revision']}:{selected['kind']}:{selected['id']}".encode()
    ).hexdigest()[:20]
    return _envelope(
        context,
        "generate_ct_evidence_slices",
        {"selected_element": {"kind": selected["kind"], "id": selected["id"]}},
        evidence=[
            {
                "artifact_id": f"evidence_{artifact_key}",
                "kind": "dash_raw_ct_review",
                "viewer_action": {"type": "select_element", "element": {"kind": selected["kind"], "id": selected["id"]}},
                "description": "Selects the element and refreshes Dash's existing full-resolution raw-CT evidence panels.",
            }
        ],
    )


def compare_expected_geometry_with_ct(context_id: str) -> dict[str, Any]:
    inspected = inspect_selected_element(context_id)
    context = _context(context_id)
    selected = inspected["summary"]["selected"]
    if selected["kind"] != "strut":
        raise HTTPException(status_code=409, detail="Expected-versus-CT comparison currently requires a selected strut.")
    return _envelope(
        context,
        "compare_expected_geometry_with_ct",
        {
            "strut_id": selected["id"],
            "expected_geometry": "registered design centerline",
            "observed_support_fraction": selected.get("skeleton_support_fraction"),
            "observed_material_fraction": selected.get("present_fraction"),
            "measured_thickness_um": selected.get("measured_thickness_um"),
            "classification": selected.get("status"),
        },
        elements=[selected],
        warnings=["Comparison uses the registered graph and persisted CT-derived analysis artifacts."],
    )


def summarize_visible_defects(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    visible = _visible_records(context, _analysis(context))
    counts = Counter(str(record.get("status")) for _, record in visible)
    flagged = [
        _compact_element(record, kind)
        for kind, record in visible
        if record.get("status") not in {"healthy", None}
    ]
    return _envelope(
        context,
        "summarize_visible_defects",
        {"visible_element_count": len(visible), "status_counts": dict(sorted(counts.items())), "flagged_count": len(flagged)},
        elements=flagged[:100],
        warnings=["Counts are limited to the current displayed bounds and filters."],
    )


def create_viewport_nde_report(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    defects = summarize_visible_defects(context_id)
    connectivity = analyze_connectivity_in_bounds(context_id)
    settings = get_settings()
    report_payload = {
        "report_version": "1",
        "created_at": datetime.now(UTC).isoformat(),
        "context": context.model_dump(mode="json"),
        "visible_defects": defects,
        "connectivity": connectivity,
    }
    artifact_id = f"report_{hashlib.sha256(json.dumps(report_payload, sort_keys=True).encode()).hexdigest()[:20]}"
    target = settings.copilot_artifact_root / f"{artifact_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    return _envelope(
        context,
        "create_viewport_nde_report",
        {"artifact_id": artifact_id, "format": "json", "report_scope": _scope(context)},
        evidence=[{"artifact_id": artifact_id, "href": f"/v1/copilot/artifacts/{artifact_id}", "kind": "nde_report"}],
    )


TOOL_REGISTRY = {
    "get_current_viewport_context": get_current_viewport_context,
    "list_visible_elements": list_visible_elements,
    "analyze_connectivity_in_bounds": analyze_connectivity_in_bounds,
    "identify_disconnected_components": identify_disconnected_components,
    "inspect_selected_element": inspect_selected_element,
    "generate_ct_evidence_slices": generate_ct_evidence_slices,
    "compare_expected_geometry_with_ct": compare_expected_geometry_with_ct,
    "summarize_visible_defects": summarize_visible_defects,
    "create_viewport_nde_report": create_viewport_nde_report,
}

