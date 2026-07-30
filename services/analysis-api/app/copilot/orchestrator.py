"""Tool-first copilot orchestration with an optional OpenAI Responses narrator."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from app.core.config import get_settings

from .store import viewport_context_store
from .tools import (
    analyze_connectivity_in_bounds,
    compare_expected_geometry_with_ct,
    create_viewport_nde_report,
    generate_ct_evidence_slices,
    identify_disconnected_components,
    inspect_selected_element,
    summarize_visible_defects,
)


def _tool_plan(message: str) -> list[tuple[str, Any]]:
    normalized = message.lower()
    if "full selected-element evidence review" in normalized:
        return [
            ("inspect_selected_element", inspect_selected_element),
            ("compare_expected_geometry_with_ct", compare_expected_geometry_with_ct),
            ("generate_ct_evidence_slices", generate_ct_evidence_slices),
        ]
    if any(word in normalized for word in ("report", "nde report", "export")):
        return [("create_viewport_nde_report", create_viewport_nde_report)]
    if any(word in normalized for word in ("evidence", "ct slice", "raw ct")):
        return [("generate_ct_evidence_slices", generate_ct_evidence_slices)]
    if any(word in normalized for word in ("compare", "expected", "design geometry")):
        return [("compare_expected_geometry_with_ct", compare_expected_geometry_with_ct)]
    if any(word in normalized for word in ("why", "classified", "selected", "this strut", "this node")):
        return [("inspect_selected_element", inspect_selected_element)]
    if any(word in normalized for word in ("show disconnected", "disconnected component")):
        return [
            ("analyze_connectivity_in_bounds", analyze_connectivity_in_bounds),
            ("identify_disconnected_components", identify_disconnected_components),
        ]
    if any(word in normalized for word in ("defect", "visible")):
        return [("summarize_visible_defects", summarize_visible_defects)]
    return [("analyze_connectivity_in_bounds", analyze_connectivity_in_bounds)]


def _local_narrative(message: str, results: list[dict[str, Any]]) -> str:
    if "full selected-element evidence review" in message.lower():
        inspected = next(result for result in results if result["tool_name"] == "inspect_selected_element")
        selected = inspected["summary"]["selected"]
        comparison = next(
            (result["summary"] for result in results if result["tool_name"] == "compare_expected_geometry_with_ct"),
            None,
        )
        details = (
            f"{selected['kind'].title()} {selected['id']} is classified as {selected.get('status')}. "
            f"Its recorded rule strength is {selected.get('rule_strength')}; this is a decision margin, not a probability."
        )
        if selected["kind"] == "strut" and comparison:
            details += (
                f" Registered-centerline comparison reports material support {comparison.get('observed_material_fraction')}, "
                f"skeleton support {comparison.get('observed_support_fraction')}, and measured thickness "
                f"{comparison.get('measured_thickness_um')} µm."
            )
        details += " The raw-CT evidence panel has been refreshed for close review."
        return details
    result = results[-1]
    tool = result["tool_name"]
    summary = result["summary"]
    scope = result["scope"]
    if tool == "analyze_connectivity_in_bounds":
        return (
            f"For the displayed region, {summary['visible_strut_count']} visible struts form "
            f"{summary['induced_design_component_count']} induced design component(s). "
            f"Their CT support maps to {summary['ct_component_count_in_visible_struts']} component(s), "
            f"with {summary['disconnected_visible_strut_count']} visible strut(s) on a non-main component. "
            "This is scoped to your active bounds and filters, not the entire lattice."
        )
    if tool == "identify_disconnected_components":
        return f"I found {summary['disconnected_component_count']} disconnected CT component(s) in the displayed scope. Use the highlighted element IDs to inspect them."
    if tool == "summarize_visible_defects":
        return f"The visible scope contains {summary['flagged_count']} flagged element(s). Status counts: {summary['status_counts']}."
    if tool == "inspect_selected_element":
        selected = summary["selected"]
        return (
            f"{selected['kind'].title()} {selected['id']} is classified as {selected.get('status')}. "
            f"The recorded rule strength is {selected.get('rule_strength')}; it is a decision margin, not a probability."
        )
    if tool == "compare_expected_geometry_with_ct":
        return (
            f"Strut {summary['strut_id']} is compared against its registered design centerline. "
            f"Material support is {summary.get('observed_material_fraction')}, skeleton support is "
            f"{summary.get('observed_support_fraction')}, and the current classification is {summary.get('classification')}."
        )
    if tool == "generate_ct_evidence_slices":
        return "I selected the requested element. The existing raw-CT evidence panel below the viewer has been refreshed with its orthogonal and cross-section evidence."
    if tool == "create_viewport_nde_report":
        return f"Created viewport-scoped NDE report {summary['artifact_id']}."
    return "The requested deterministic analysis completed."


def _openai_narrative(message: str, results: list[dict[str, Any]]) -> str | None:
    """Use OpenAI only as a narrator; tool results remain the scientific source."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.responses.create(
            model=settings.copilot_model,
            reasoning={"effort": settings.copilot_reasoning_effort},
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a lattice CT copilot. Use only the supplied deterministic tool results "
                        "for scientific claims. State that findings are viewport-scoped, retain numeric "
                        "values and element IDs, and do not infer unprovided CT evidence. Keep the answer concise."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {message}\n\nTool results:\n{json.dumps(results, ensure_ascii=False)}",
                },
            ],
        )
        text = getattr(response, "output_text", "").strip()
        return text or None
    except Exception:
        # Local work and scientific analysis must remain usable without a model service.
        return None


def run_copilot(message: str, context_id: str) -> dict[str, Any]:
    context = viewport_context_store.get(context_id)
    run_id = f"crun_{secrets.token_urlsafe(12)}"
    results: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    full_selected_review = "full selected-element evidence review" in message.lower()
    for name, tool in _tool_plan(message):
        try:
            result = tool(context_id)
        except HTTPException as exc:
            if full_selected_review and name == "compare_expected_geometry_with_ct" and exc.status_code == 409:
                continue
            raise
        results.append(result)
        for evidence in result.get("evidence", []):
            action = evidence.get("viewer_action")
            if action:
                actions.append(action)
        if result["tool_name"] == "identify_disconnected_components":
            ids = [element_id for component in result["elements"] for element_id in component.get("visible_strut_ids", [])]
            if ids:
                actions.append({"type": "highlight_elements", "kind": "strut", "ids": ids[:100]})
    answer = _openai_narrative(message, results) or _local_narrative(message, results)
    record = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "message": message,
        "context_id": context_id,
        "context_fingerprint": context.fingerprint,
        "dataset_id": context.dataset_id,
        "model": get_settings().copilot_model if get_settings().openai_api_key else "deterministic-local-narrator",
        "tool_results": results,
        "answer": answer,
        "viewer_actions": actions,
    }
    root = get_settings().copilot_artifact_root / "runs"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{run_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
