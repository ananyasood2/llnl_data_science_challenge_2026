"""Compact deterministic tools shared by MCP and the runtime orchestrator."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import HTTPException

from app.core.config import get_settings
from app.repositories.measurements import (
    MeasurementDatasetNotFoundError,
    MeasurementPrerequisiteError,
    MeasurementStrutNotFoundError,
    measurement_repository,
)

from .contracts import (
    MeasurementContextCreate,
    MeasurementToolEnvelope,
    StoredMeasurementContext,
)
from .store import measurement_context_store


ToolFunction = Callable[..., dict[str, Any]]


def create_measurement_context(
    dataset_id: str = "missing_struts",
    target_thickness_um: float = 350.0,
    critical_cutoff_um: float = 300.0,
    user_cutoff_um: float = 350.0,
    target_density_percent: float = 10.0,
    selected_strut_id: int | str | None = None,
    visible_statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Create the immutable context required by dataset-scoped measurement tools."""

    try:
        payload = MeasurementContextCreate(
            dataset_id=dataset_id,
            target_thickness_um=target_thickness_um,
            critical_cutoff_um=critical_cutoff_um,
            user_cutoff_um=user_cutoff_um,
            target_density_percent=target_density_percent,
            selected_strut_id=selected_strut_id,
            visible_statuses=visible_statuses or [],
        )
        revision = measurement_repository.revision(payload.dataset_id)
        if payload.selected_strut_id is not None:
            payload.selected_strut_id = measurement_repository.resolve_strut_id(
                payload.dataset_id,
                payload.selected_strut_id,
            )
    except (MeasurementDatasetNotFoundError, MeasurementStrutNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeasurementPrerequisiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return measurement_context_store.put(payload, revision).model_dump(mode="json")


def _context(context_id: str) -> StoredMeasurementContext:
    context = measurement_context_store.get(context_id)
    try:
        current_revision = measurement_repository.revision(context.dataset_id)
    except MeasurementDatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeasurementPrerequisiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if current_revision != context.analysis_revision:
        raise HTTPException(
            status_code=409,
            detail="The measurement analysis changed. Refresh the page to capture a new context.",
        )
    return context


def _scope(context: StoredMeasurementContext) -> dict[str, Any]:
    return {
        "target_thickness_um": context.target_thickness_um,
        "critical_cutoff_um": context.critical_cutoff_um,
        "user_cutoff_um": context.user_cutoff_um,
        "target_density_percent": context.target_density_percent,
        "selected_strut_id": context.selected_strut_id,
        "visible_statuses": context.visible_statuses,
    }


def _envelope(
    context: StoredMeasurementContext,
    tool_name: str,
    specialist: str,
    summary: dict[str, Any],
    *,
    elements: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload = MeasurementToolEnvelope(
        tool_run_id=f"mtool_{secrets.token_urlsafe(10)}",
        tool_name=tool_name,
        specialist=specialist,
        context_id=context.context_id,
        dataset_id=context.dataset_id,
        analysis_revision=context.analysis_revision,
        scope=_scope(context),
        summary=summary,
        elements=elements or [],
        evidence=evidence or [],
        warnings=warnings or [],
        provenance={
            "context_fingerprint": context.fingerprint,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "deterministic_measurement_repository",
        },
    )
    return payload.model_dump(mode="json")


def _summary(context: StoredMeasurementContext) -> dict[str, Any]:
    return measurement_repository.summary(
        context.dataset_id,
        target_thickness_um=context.target_thickness_um,
        critical_cutoff_um=context.critical_cutoff_um,
        user_cutoff_um=context.user_cutoff_um,
        target_density_percent=context.target_density_percent,
        include_map=False,
    )


def get_measurement_context(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    return _envelope(
        context,
        "get_measurement_context",
        "Measurement Orchestrator",
        {
            "fingerprint": context.fingerprint,
            "captured_at": context.captured_at.isoformat(),
            "expires_at": context.expires_at.isoformat(),
            "qualified": True,
        },
    )


def get_thickness_summary(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    result = _summary(context)
    return _envelope(
        context,
        "get_thickness_summary",
        "Thickness Analysis Agent",
        result["thickness"],
        warnings=result["warnings"],
    )


def list_out_of_spec_struts(
    context_id: str,
    cutoff_um: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    context = _context(context_id)
    try:
        result = measurement_repository.outliers(
            context.dataset_id,
            cutoff_um=context.user_cutoff_um if cutoff_um is None else cutoff_um,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    struts = result.pop("struts")
    return _envelope(
        context,
        "list_out_of_spec_struts",
        "Thickness Analysis Agent",
        {
            key: value
            for key, value in result.items()
            if key not in {"dataset_id", "analysis_revision"}
        },
        elements=struts,
        evidence=[
            {
                "kind": "viewer_action",
                "action": "highlight_struts",
                "strut_ids": [item["strut_id"] for item in struts],
            }
        ],
    )


def inspect_selected_strut(context_id: str) -> dict[str, Any]:
    """Inspect only the strut captured by the immutable measurement context."""

    context = _context(context_id)
    if context.selected_strut_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "The measurement context has no selected_strut_id. Select a registered "
                "strut and create a new context before inspecting it."
            ),
        )
    try:
        result = measurement_repository.strut_detail(
            context.dataset_id,
            context.selected_strut_id,
            expected_analysis_revision=context.analysis_revision,
            target_thickness_um=context.target_thickness_um,
            critical_cutoff_um=context.critical_cutoff_um,
            user_cutoff_um=context.user_cutoff_um,
        )
    except MeasurementStrutNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeasurementPrerequisiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    neighbors = result["neighbors"]
    selected_id = result["strut"]["strut_id"]
    return _envelope(
        context,
        "inspect_selected_strut",
        "Thickness Analysis Agent",
        {
            "unit": result["unit"],
            "method": result["method"],
            "method_version": result["method_version"],
            "eligibility_rule": result["eligibility_rule"],
            "eligible_strut_count": result["eligible_strut_count"],
            "excluded_strut_count": result["excluded_strut_count"],
            "strut": result["strut"],
            "neighbors": {
                key: value for key, value in neighbors.items() if key != "struts"
            },
        },
        elements=[
            {
                "element_role": "selected",
                "strut_id": result["strut"]["strut_id"],
                "analysis_status": result["strut"]["analysis_status"],
                "measured_thickness_um": result["strut"]["measured_thickness_um"],
                "design_thickness_um": result["strut"]["design_thickness_um"],
            },
            *[
                {"element_role": "neighbor", **neighbor}
                for neighbor in neighbors["struts"][:49]
            ],
        ],
        evidence=[
            {
                "kind": "viewer_action",
                "action": "highlight_struts",
                "strut_ids": [selected_id],
            }
        ],
        warnings=result["warnings"],
    )


def get_relative_density(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    result = _summary(context)
    return _envelope(
        context,
        "get_relative_density",
        "Relative Density Agent",
        result["relative_density"],
        warnings=result["warnings"],
    )


def compare_measurements_to_design(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    result = _summary(context)
    return _envelope(
        context,
        "compare_measurements_to_design",
        "Measurement Orchestrator",
        {
            **result["comparison"],
            "key_measurements": {
                "median_thickness_um": result["thickness"]["median_um"],
                "percent_below_target": result["thickness"]["below_target"]["percent"],
                "percent_below_critical": result["thickness"]["below_critical"]["percent"],
                "relative_density_percent": result["relative_density"]["relative_density_percent"],
            },
        },
        warnings=result["warnings"],
    )


def analyze_measurement_sensitivity(
    context_id: str,
    cutoffs_um: list[float] | None = None,
) -> dict[str, Any]:
    context = _context(context_id)
    cutoffs = cutoffs_um or sorted(
        {
            context.critical_cutoff_um,
            context.user_cutoff_um,
            context.target_thickness_um,
        }
    )
    try:
        result = measurement_repository.sensitivity(
            context.dataset_id,
            cutoffs_um=cutoffs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _envelope(
        context,
        "analyze_measurement_sensitivity",
        "Thickness Analysis Agent",
        {
            key: value
            for key, value in result.items()
            if key not in {"dataset_id", "analysis_revision"}
        },
        warnings=[
            "This compares cutoff choices on one persisted measurement distribution; it does not rerun CT segmentation."
        ],
    )


def create_measurement_report(context_id: str) -> dict[str, Any]:
    context = _context(context_id)
    result = _summary(context)
    report_identity = {
        "report_version": "1",
        "dataset_id": context.dataset_id,
        "analysis_revision": context.analysis_revision,
        "context": _scope(context),
    }
    report_payload = {
        **report_identity,
        "created_at": datetime.now(UTC).isoformat(),
        "thickness": result["thickness"],
        "relative_density": result["relative_density"],
        "comparison": result["comparison"],
        "warnings": result["warnings"],
        "provenance": result["provenance"],
    }
    digest = hashlib.sha256(
        json.dumps(report_identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    artifact_id = f"measurement_report_{digest}"
    artifact_root = get_settings().measurement_artifact_root / "reports"
    artifact_root.mkdir(parents=True, exist_ok=True)
    json_path = artifact_root / f"{artifact_id}.json"
    markdown_path = artifact_root / f"{artifact_id}.md"
    if not json_path.exists():
        json_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    if not markdown_path.exists():
        markdown_path.write_text(
            "\n".join(
                [
                    "# Lattice CT Measurement Report",
                    "",
                    f"- Dataset: `{context.dataset_id}`",
                    f"- Analysis revision: `{context.analysis_revision}`",
                    f"- Overall comparison: **{result['comparison']['overall_status'].upper()}**",
                    f"- Median thickness: {result['thickness']['median_um']} µm",
                    f"- Below {context.target_thickness_um} µm: {result['thickness']['below_target']['percent']}%",
                    f"- Below {context.critical_cutoff_um} µm: {result['thickness']['below_critical']['percent']}%",
                    f"- Relative density: {result['relative_density']['relative_density_percent']}%",
                    f"- Target relative density: {context.target_density_percent}%",
                    "",
                    "## Limitations",
                    "",
                    *[f"- {warning}" for warning in result["warnings"]],
                ]
            ),
            encoding="utf-8",
        )
    return _envelope(
        context,
        "create_measurement_report",
        "Measurement Orchestrator",
        {"artifact_id": artifact_id, "formats": ["json", "markdown"]},
        evidence=[
            {
                "artifact_id": artifact_id,
                "kind": "measurement_report",
                "href": f"/v1/measurement-copilot/artifacts/{artifact_id}",
            }
        ],
    )


TOOL_REGISTRY: dict[str, ToolFunction] = {
    "create_measurement_context": create_measurement_context,
    "get_measurement_context": get_measurement_context,
    "get_thickness_summary": get_thickness_summary,
    "list_out_of_spec_struts": list_out_of_spec_struts,
    "inspect_selected_strut": inspect_selected_strut,
    "get_relative_density": get_relative_density,
    "compare_measurements_to_design": compare_measurements_to_design,
    "analyze_measurement_sensitivity": analyze_measurement_sensitivity,
    "create_measurement_report": create_measurement_report,
}
