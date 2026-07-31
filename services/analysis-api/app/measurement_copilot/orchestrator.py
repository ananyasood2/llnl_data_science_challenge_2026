"""Tool-calling measurement copilot with a deterministic offline fallback."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

from .contracts import MeasurementCopilotResponse
from .store import measurement_context_store
from .tools import TOOL_REGISTRY


SYSTEM_PROMPT = """You are the Measurement Copilot for registered lattice CT inspection.
The backend tools are the only scientific authority. Never calculate, estimate, or invent a
measurement yourself. Use Thickness Analysis Agent tools for distributions, cutoffs, and
strut rankings. For a selected/clicked strut, use inspect_selected_strut; it is bound to the
immutable context selection, and its neighbors mean shared registered endpoint nodes only,
not geometric proximity or causal dependence. Use Relative Density Agent tools for
segmented/enclosing volume and density.
For broad design-match questions, obtain thickness, density, policy comparison, and relevant
outliers before answering. State that pass/warn/fail is provisional. Cite claims as
[tool_name:tool_run_id]. Return a concise engineering conclusion, evidence, caveat, and next action.
Do not request or expose raw CT arrays or server paths."""


OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_measurement_context",
        "description": "Get the immutable measurement scope and qualified analysis revision.",
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_thickness_summary",
        "description": "Get deterministic strut thickness statistics and histogram evidence.",
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "inspect_selected_strut",
        "description": (
            "Inspect the strut already selected in the immutable context, including its "
            "persisted measurement, weak-ECDF rank, cutoffs, and shared-endpoint neighbors."
        ),
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_out_of_spec_struts",
        "description": "Rank a bounded list of registered struts below a thickness cutoff.",
        "parameters": {
            "type": "object",
            "properties": {
                "context_id": {"type": "string"},
                "cutoff_um": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["context_id", "cutoff_um", "limit"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_relative_density",
        "description": "Get segmented volume, enclosing registered ROI volume, and relative density.",
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "compare_measurements_to_design",
        "description": "Compare deterministic thickness and density measurements with the explicit provisional policy.",
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "analyze_measurement_sensitivity",
        "description": "Compare percent-below results across user-selected thickness cutoffs.",
        "parameters": {
            "type": "object",
            "properties": {
                "context_id": {"type": "string"},
                "cutoffs_um": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 20},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["context_id", "cutoffs_um"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_measurement_report",
        "description": "Create immutable JSON and Markdown reports from cited measurement results.",
        "parameters": {
            "type": "object",
            "properties": {"context_id": {"type": "string"}},
            "required": ["context_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _is_selected_strut_question(message: str) -> bool:
    normalized = message.lower()
    return any(
        phrase in normalized
        for phrase in (
            "selected strut",
            "clicked strut",
            "this strut",
            "this element",
            "its neighbors",
            "neighboring struts",
            "neighbor struts",
            "percentile rank",
            "where does it rank",
        )
    )


def _local_plan(
    message: str,
    *,
    selected_strut_available: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    normalized = message.lower()
    broad = any(
        phrase in normalized
        for phrase in (
            "match the intended",
            "match intended",
            "statistically",
            "overall",
            "design expectations",
            "does this print",
        )
    )
    if _is_selected_strut_question(message) and selected_strut_available:
        return [("inspect_selected_strut", {})]
    if any(word in normalized for word in ("report", "export", "download")):
        return [
            ("get_thickness_summary", {}),
            ("get_relative_density", {}),
            ("compare_measurements_to_design", {}),
            ("create_measurement_report", {}),
        ]
    if any(
        word in normalized
        for word in ("what if", "what changes", "change if", "sensitivity", "cutoff choices")
    ):
        return [
            ("get_thickness_summary", {}),
            ("analyze_measurement_sensitivity", {"cutoffs_um": None}),
        ]
    if broad:
        return [
            ("get_thickness_summary", {}),
            ("get_relative_density", {}),
            ("compare_measurements_to_design", {}),
            ("list_out_of_spec_struts", {"cutoff_um": None, "limit": 10}),
        ]
    if any(word in normalized for word in ("worst", "outlier", "highlight", "show thin")):
        return [("list_out_of_spec_struts", {"cutoff_um": None, "limit": 10})]
    if any(word in normalized for word in ("density", "volume", "10%")):
        return [
            ("get_relative_density", {}),
            ("compare_measurements_to_design", {}),
        ]
    if any(word in normalized for word in ("thickness", "micron", "histogram", "thin")):
        return [
            ("get_thickness_summary", {}),
            ("list_out_of_spec_struts", {"cutoff_um": None, "limit": 10}),
        ]
    return [
        ("get_thickness_summary", {}),
        ("get_relative_density", {}),
        ("compare_measurements_to_design", {}),
    ]


def _execute_tool(name: str, arguments: dict[str, Any], context_id: str) -> dict[str, Any]:
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown measurement tool {name!r}")
    safe_arguments = dict(arguments)
    safe_arguments["context_id"] = context_id
    if name == "list_out_of_spec_struts":
        safe_arguments["limit"] = max(1, min(50, int(safe_arguments.get("limit", 10))))
    return TOOL_REGISTRY[name](**safe_arguments)


def _viewer_actions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for result in results:
        for evidence in result.get("evidence", []):
            if evidence.get("action") == "highlight_struts":
                actions.append(
                    {
                        "type": "highlight_struts",
                        "strut_ids": evidence.get("strut_ids", [])[:50],
                    }
                )
    return actions


def _citation(result: dict[str, Any]) -> str:
    return f"[{result['tool_name']}:{result['tool_run_id']}]"


def _local_answer(message: str, results: list[dict[str, Any]]) -> str:
    by_name = {result["tool_name"]: result for result in results}
    comparison = by_name.get("compare_measurements_to_design")
    thickness = by_name.get("get_thickness_summary")
    density = by_name.get("get_relative_density")
    sensitivity = by_name.get("analyze_measurement_sensitivity")
    outliers = by_name.get("list_out_of_spec_struts")
    selected = by_name.get("inspect_selected_strut")
    report = by_name.get("create_measurement_report")

    if report:
        artifact_id = report["summary"]["artifact_id"]
        return (
            f"Created traceable measurement report `{artifact_id}` from analysis revision "
            f"`{report['analysis_revision'][:12]}`. {_citation(report)}"
        )
    if sensitivity:
        values = ", ".join(
            f"{item['cutoff_um']:g} µm → {item['percent_below']:.3f}%"
            for item in sensitivity["summary"]["results"]
        )
        return (
            f"Cutoff sensitivity for the persisted thickness distribution: {values}. "
            "This changes the comparison cutoff, not the CT segmentation. "
            f"{_citation(sensitivity)}"
        )
    if selected:
        summary = selected["summary"]
        strut = summary["strut"]
        neighbors = summary["neighbors"]
        if not strut["measurement_eligible"]:
            answer = (
                f"Selected strut `{strut['strut_id']}` has persisted analysis status "
                f"`{strut['analysis_status']}` but no eligible measured thickness, so its "
                "percentile and cutoff differences are unavailable."
            )
        else:
            target = strut["target_comparison"]
            critical = strut["critical_cutoff_comparison"]
            user_cutoff = strut["user_cutoff_comparison"]
            percentile = strut["percentile"]
            answer = (
                f"Selected strut `{strut['strut_id']}` has persisted analysis status "
                f"`{strut['analysis_status']}` and measures "
                f"{strut['measured_thickness_um']:.3f} µm "
                f"({target['difference_um']:+.3f} µm versus the "
                f"{target['target_um']:.3f} µm target). It is "
                f"{'below' if critical['below'] else 'not below'} the "
                f"{critical['cutoff_um']:.3f} µm critical cutoff "
                f"({critical['difference_um']:+.3f} µm) and "
                f"{'below' if user_cutoff['below'] else 'not below'} the active "
                f"{user_cutoff['cutoff_um']:.3f} µm user cutoff "
                f"({user_cutoff['difference_um']:+.3f} µm). Its weak-ECDF rank is "
                f"{percentile['rank_percent']:.3f}% among "
                f"{percentile['population_count']} eligible struts."
            )
        answer += (
            f" Of {neighbors['total_count']} registered shared-endpoint neighbors, "
            f"{neighbors['eligible_count']} have eligible measured thickness and "
            f"{neighbors['excluded_count']} are excluded."
        )
        if neighbors["median_thickness_um"] is not None:
            answer += (
                f" The median across the {neighbors['eligible_count']} measured neighbors is "
                f"{neighbors['median_thickness_um']:.3f} µm"
            )
            if neighbors["selected_minus_median_um"] is not None:
                answer += (
                    f"; the selected strut is "
                    f"{neighbors['selected_minus_median_um']:+.3f} µm from that median."
                )
            else:
                answer += "."
        else:
            answer += " A measured-neighbor median comparison is unavailable."
        return answer + (
            f" Evidence is qualified to analysis revision "
            f"`{selected['analysis_revision'][:12]}`. {_citation(selected)}"
        ) + (
            " Neighbor comparison is registered one-hop topology only; it does not imply "
            "geometric proximity, causality, or statistical independence."
        )
    if comparison:
        summary = comparison["summary"]
        metrics = summary["key_measurements"]
        driver = (
            "thickness"
            if summary["thickness_status"] == "fail"
            and summary["relative_density_status"] != "fail"
            else "relative density"
            if summary["relative_density_status"] == "fail"
            and summary["thickness_status"] != "fail"
            else "both thickness and relative density"
        )
        answer = (
            f"The provisional design comparison is **{summary['overall_status'].upper()}**, "
            f"driven by {driver}. Median thickness is {metrics['median_thickness_um']:.3f} µm; "
            f"{metrics['percent_below_target']:.3f}% of eligible struts are below the target and "
            f"{metrics['percent_below_critical']:.3f}% are below the critical cutoff. Relative "
            f"density is {metrics['relative_density_percent']:.3f}%. {_citation(comparison)}"
        )
        if outliers and outliers["elements"]:
            ids = ", ".join(str(item["strut_id"]) for item in outliers["elements"][:10])
            answer += f" The ten lowest-thickness struts are {ids}; they are highlighted on the map. {_citation(outliers)}"
        answer += " Pass/warn/fail uses a demo policy, not an approved acceptance decision."
        return answer
    if density:
        summary = density["summary"]
        return (
            f"Relative density is {summary['relative_density_percent']:.3f}% versus the "
            f"{summary['target_percent']:.3f}% target. Segmented volume is "
            f"{summary['segmented_volume_mm3']:.3f} mm³ within a "
            f"{summary['enclosing_volume_mm3']:.3f} mm³ registered ROI. {_citation(density)}"
        )
    if thickness:
        summary = thickness["summary"]
        answer = (
            f"Median strut thickness is {summary['median_um']:.3f} µm and mean thickness is "
            f"{summary['mean_um']:.3f} µm. {summary['below_target']['percent']:.3f}% are below "
            f"{summary['target_um']:.3f} µm, with {summary['excluded_strut_count']} unmeasured "
            f"struts excluded. {_citation(thickness)}"
        )
        if outliers and outliers["elements"]:
            answer += f" I highlighted the {len(outliers['elements'])} lowest-thickness returned struts. {_citation(outliers)}"
        return answer
    return "No deterministic measurement result was available, so I cannot make a scientific claim."


def _run_local(message: str, context_id: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    context = measurement_context_store.get(context_id)
    results = [
        _execute_tool(name, arguments, context_id)
        for name, arguments in _local_plan(
            message,
            selected_strut_available=context.selected_strut_id is not None,
        )
    ]
    return _local_answer(message, results), results, []


def _run_openai(message: str, context_id: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    inputs: list[Any] = [
        {
            "role": "user",
            "content": (
                f"Measurement context ID: {context_id}\n"
                f"Question: {message}"
            ),
        }
    ]
    results: list[dict[str, Any]] = []
    warnings: list[str] = []
    context = measurement_context_store.get(context_id)
    selected_result_required = (
        context.selected_strut_id is not None and _is_selected_strut_question(message)
    )
    for _ in range(6):
        response = client.responses.create(
            model=settings.measurement_copilot_model,
            instructions=SYSTEM_PROMPT,
            input=inputs,
            tools=OPENAI_TOOLS,
            reasoning={"effort": settings.measurement_copilot_reasoning_effort},
            text={"verbosity": "medium"},
        )
        calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not calls:
            text = str(getattr(response, "output_text", "")).strip()
            if results and text:
                if not selected_result_required:
                    return text, results, warnings
                selected_results = [
                    result
                    for result in results
                    if result["tool_name"] == "inspect_selected_strut"
                ]
                if any(_citation(result) in text for result in selected_results):
                    return text, results, warnings
                if not selected_results:
                    selected_result = _execute_tool(
                        "inspect_selected_strut",
                        {},
                        context_id,
                    )
                    results = [selected_result]
                warnings.append(
                    "The model response omitted required selected-strut evidence or "
                    "its exact citation; deterministic narration was used."
                )
                return _local_answer(message, results), results, warnings
            break
        inputs.extend(response.output)
        for call in calls:
            if len(results) >= 10:
                warnings.append("Tool-call safety limit reached after ten deterministic calls.")
                break
            arguments = json.loads(call.arguments or "{}")
            result = _execute_tool(call.name, arguments, context_id)
            results.append(result)
            inputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )
    if not results:
        local_answer, results, local_warnings = _run_local(message, context_id)
        warnings.extend(local_warnings)
        warnings.append("The model returned no tool evidence; deterministic routing was used.")
        return local_answer, results, warnings
    if selected_result_required:
        selected_result = next(
            (
                result
                for result in results
                if result["tool_name"] == "inspect_selected_strut"
            ),
            None,
        )
        if selected_result is None:
            selected_result = _execute_tool("inspect_selected_strut", {}, context_id)
            results = [selected_result]
        warnings.append(
            "The model did not return a supported selected-strut answer; "
            "deterministic narration was used."
        )
        return _local_answer(message, results), results, warnings
    warnings.append("The model response was incomplete; a deterministic evidence summary was used.")
    return _local_answer(message, results), results, warnings


def run_measurement_copilot(message: str, context_id: str) -> dict[str, Any]:
    context = measurement_context_store.get(context_id)
    settings = get_settings()
    mode = "deterministic-local-orchestrator"
    model = "deterministic-local-orchestrator"
    if settings.openai_api_key:
        try:
            answer, results, warnings = _run_openai(message, context_id)
            mode = "openai-tool-calling"
            model = settings.measurement_copilot_model
        except Exception as exc:
            answer, results, warnings = _run_local(message, context_id)
            warnings.append(
                f"OpenAI tool-calling was unavailable; deterministic routing completed the run ({type(exc).__name__})."
            )
    else:
        answer, results, warnings = _run_local(message, context_id)

    created_at = datetime.now(UTC)
    record = MeasurementCopilotResponse(
        run_id=f"mrun_{secrets.token_urlsafe(12)}",
        context_id=context_id,
        dataset_id=context.dataset_id,
        analysis_revision=context.analysis_revision,
        created_at=created_at,
        mode=mode,
        model=model,
        answer=answer,
        tool_results=results,
        viewer_actions=_viewer_actions(results),
        warnings=warnings,
    ).model_dump(mode="json")
    run_root = settings.measurement_artifact_root / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / f"{record['run_id']}.json").write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )
    return record
