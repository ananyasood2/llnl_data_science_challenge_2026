"""Interactive 3D comparison of a CT lattice scan and its registered design."""

from __future__ import annotations

import argparse
import math
import sys
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from skimage import measure

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (str(REPO_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.datasets import DATASETS, get_dataset  # noqa: E402
from lattice_pipeline.cache import ensure_analysis, load_cached_arrays  # noqa: E402


STATUS_ORDER = ("healthy", "thick", "thin", "missing", "uncertain")
FILTER_ORDER = ("missing", "uncertain", "thin", "thick", "healthy")
STATUS_COLORS = {
    "healthy": "#7f9aa8",
    "missing": "#ff4868",
    "uncertain": "#4da3ff",
    "thin": "#ffb547",
    "thick": "#a978ff",
}
STATUS_LABELS = {
    "healthy": "Healthy",
    "missing": "Missing",
    "uncertain": "Boundary / uncertain",
    "thin": "Thin",
    "thick": "Thick",
}
AXIS_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")

_MAX_CACHED_ANALYSES = 8
_ANALYSES: OrderedDict[
    tuple[str, float, float | None],
    dict[str, Any],
] = OrderedDict()
_ANALYSIS_LOCK = RLock()


def _analysis(
    dataset_key: str,
    voxel_size: float,
    threshold: float | None = None,
) -> dict[str, Any]:
    threshold_key = None if threshold is None else round(float(threshold), 12)
    key = (dataset_key, round(float(voxel_size), 9), threshold_key)
    with _ANALYSIS_LOCK:
        cached = _ANALYSES.get(key)
        if cached is not None:
            _ANALYSES.move_to_end(key)
            return cached

        analysis = ensure_analysis(
            dataset_key,
            get_dataset(dataset_key),
            threshold=threshold,
            voxel_size_mm=float(voxel_size),
        )
        # Processed mask files hold the most recently computed threshold. Keep
        # the corresponding browser-sized mesh with the analysis so switching
        # back to any recent threshold never reads a mismatched mask or repeats
        # the expensive pipeline.
        analysis["_display_geometry"] = _display_geometry(
            dataset_key,
            str(analysis["meta"]["cache_fingerprint"]),
        )
        _ANALYSES[key] = analysis
        _ANALYSES.move_to_end(key)
        while len(_ANALYSES) > _MAX_CACHED_ANALYSES:
            _ANALYSES.popitem(last=False)
        return analysis


def _axis_indices(axis_order: str) -> tuple[int, int, int]:
    normalized = str(axis_order).upper()
    if normalized not in AXIS_ORDERS:
        raise ValueError(
            f"Unknown axis order {axis_order!r}; choose from {', '.join(AXIS_ORDERS)}"
        )
    source_indices = {"X": 0, "Y": 1, "Z": 2}
    return tuple(source_indices[axis] for axis in normalized)


def _reorder_xyz(points_xyz: Any, axis_order: str) -> np.ndarray:
    """Map public xyz coordinates onto the selected display-axis order."""

    points = np.asarray(points_xyz, dtype=float)
    if points.shape[-1:] != (3,):
        raise ValueError(f"Expected xyz coordinates, got shape {points.shape!r}")
    return points[..., list(_axis_indices(axis_order))]


def _format_xyz(point_xyz: Any) -> str:
    """Format one public XYZ voxel coordinate for the inspection UI."""

    point = np.asarray(point_xyz, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError(f"Expected one finite xyz coordinate, got {point_xyz!r}")
    return f"({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})"


def _strut_geometry(record: dict[str, Any]) -> dict[str, Any]:
    """Derive inspectable geometry from a strut's XYZ polyline."""

    points = np.asarray(record["polyline"], dtype=float)
    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or len(points) < 2
        or not np.all(np.isfinite(points))
    ):
        raise ValueError(
            f"Strut {record.get('id', 'unknown')} has invalid polyline coordinates"
        )

    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    length = float(segment_lengths.sum())
    if length <= 1e-12:
        midpoint = points[0].copy()
    else:
        half_length = length / 2.0
        cumulative = np.cumsum(segment_lengths)
        segment_index = int(np.searchsorted(cumulative, half_length, side="left"))
        distance_before = (
            0.0 if segment_index == 0 else float(cumulative[segment_index - 1])
        )
        segment_length = float(segment_lengths[segment_index])
        fraction = (
            0.0
            if segment_length <= 1e-12
            else (half_length - distance_before) / segment_length
        )
        midpoint = (
            points[segment_index]
            + fraction * (points[segment_index + 1] - points[segment_index])
        )

    return {
        "start": points[0],
        "end": points[-1],
        "midpoint": midpoint,
        "length": length,
    }


def _display_axis_ranges(
    axis_order: str,
    axis_maxima: dict[str, float | None] | None,
) -> tuple[list[float] | None, list[float] | None, list[float] | None]:
    """Return Plotly ranges in display order from semantic X/Y/Z maxima."""

    normalized = str(axis_order).upper()
    _axis_indices(normalized)
    maxima = axis_maxima or {}
    ranges: list[list[float] | None] = []
    for axis in normalized:
        raw_maximum = maxima.get(axis)
        if raw_maximum is None:
            ranges.append(None)
            continue
        maximum = float(raw_maximum)
        if not math.isfinite(maximum) or maximum <= 0:
            raise ValueError(f"{axis}-axis maximum must be greater than zero")
        ranges.append([0.0, maximum])
    return ranges[0], ranges[1], ranges[2]


def _axis_upper_bounds(
    axis_maxima: dict[str, float | None] | None,
) -> np.ndarray:
    """Validate semantic XYZ maxima and return an upper-bound vector."""

    ranges = _display_axis_ranges("XYZ", axis_maxima)
    return np.asarray(
        [math.inf if axis_range is None else axis_range[1] for axis_range in ranges],
        dtype=float,
    )


def _record_intersects_bounds(
    record: dict[str, Any],
    kind: str,
    upper: np.ndarray,
) -> bool:
    """Return whether a node or strut intersects an XYZ upper-bound vector."""

    if kind not in {"node", "strut"}:
        raise ValueError(f"Unknown lattice element kind {kind!r}")
    lower = np.where(np.isfinite(upper), 0.0, -math.inf)

    if kind == "node":
        point = np.asarray([record["x"], record["y"], record["z"]], dtype=float)
        return bool(np.all(point >= lower) and np.all(point <= upper))

    points = np.asarray(record["polyline"], dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError(
            f"Strut {record.get('id', 'unknown')} has invalid polyline coordinates"
        )
    if len(points) == 1:
        return bool(np.all(points[0] >= lower) and np.all(points[0] <= upper))

    # Slab intersection counts a strut whenever any displayed portion of one of
    # its polyline segments falls inside the [0, maximum] XYZ box.
    for start, end in zip(points[:-1], points[1:]):
        direction = end - start
        segment_min = 0.0
        segment_max = 1.0
        for coordinate, delta, minimum, maximum in zip(
            start,
            direction,
            lower,
            upper,
        ):
            if abs(delta) < 1e-12:
                if coordinate < minimum or coordinate > maximum:
                    break
                continue
            enter = (minimum - coordinate) / delta
            leave = (maximum - coordinate) / delta
            if enter > leave:
                enter, leave = leave, enter
            segment_min = max(segment_min, enter)
            segment_max = min(segment_max, leave)
            if segment_min > segment_max:
                break
        else:
            return True
    return False


def _record_intersects_axis_limits(
    record: dict[str, Any],
    kind: str,
    axis_maxima: dict[str, float | None] | None,
) -> bool:
    """Return whether a node or strut intersects the displayed XYZ bounds."""

    return _record_intersects_bounds(
        record,
        kind,
        _axis_upper_bounds(axis_maxima),
    )


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        showarrow=False,
        font={"color": "#9fb3bf", "size": 15},
    )
    figure.update_layout(
        height=760,
        paper_bgcolor="#071018",
        plot_bgcolor="#071018",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


@lru_cache(maxsize=8)
def _display_geometry(
    dataset_key: str,
    cache_fingerprint: str,
) -> dict[str, np.ndarray]:
    """Build a browser-sized surface from the cached CT segmentation."""

    # cache_fingerprint is intentionally part of the cache key: the mask changes
    # whenever a user applies a different segmentation threshold.
    del cache_fingerprint
    config = get_dataset(dataset_key)
    mask, _ = load_cached_arrays(config)
    stride = int(config["analysis_stride"])
    positions = np.argwhere(mask)
    minimum = positions.min(axis=0)
    maximum = positions.max(axis=0) + 1
    crop = np.asarray(mask[tuple(slice(a, b) for a, b in zip(minimum, maximum))])

    # A coarse translucent surface supplies CT context without overwhelming the
    # registered design graph or shipping the full ~1 GiB volume to the browser.
    surface_step = max(1, math.ceil(max(crop.shape) / 45))
    surface = crop[::surface_step, ::surface_step, ::surface_step]
    vertices_zyx, faces, _, _ = measure.marching_cubes(
        surface.astype(np.uint8), level=0.5
    )
    vertices_zyx = (
        vertices_zyx * (surface_step * stride) + minimum[None, :] * stride
    )
    return {
        "surface_vertices_xyz": vertices_zyx[:, ::-1],
        "surface_faces": faces,
    }


def _strut_trace(
    records: list[dict[str, Any]],
    status: str,
    axis_order: str,
) -> go.Scatter3d:
    x: list[float | None] = []
    y: list[float | None] = []
    z: list[float | None] = []
    customdata: list[list[Any]] = []
    for record in records:
        geometry = _strut_geometry(record)
        element_data = [
            "strut",
            record["id"],
            status,
            record.get("confidence", 1.0),
            geometry["midpoint"][0],
            geometry["midpoint"][1],
            geometry["midpoint"][2],
            geometry["length"],
            geometry["start"][0],
            geometry["start"][1],
            geometry["start"][2],
            geometry["end"][0],
            geometry["end"][1],
            geometry["end"][2],
        ]
        for point in record["polyline"]:
            display_point = _reorder_xyz(point, axis_order)
            x.append(display_point[0])
            y.append(display_point[1])
            z.append(display_point[2])
            customdata.append(element_data)
        x.append(None)
        y.append(None)
        z.append(None)
        customdata.append(element_data)

    width = {
        "healthy": 2.0,
        "thin": 4.0,
        "thick": 4.2,
        "missing": 5.4,
        "uncertain": 3.0,
    }[status]
    opacity = 0.54 if status == "healthy" else 0.96
    return go.Scatter3d(
        x=x,
        y=y,
        z=z,
        mode="lines",
        line={
            "color": STATUS_COLORS[status],
            "width": width,
            "dash": (
                "dot"
                if status == "missing"
                else "dash" if status == "uncertain" else "solid"
            ),
        },
        opacity=opacity,
        customdata=customdata,
        hovertemplate=(
            f"<b>{STATUS_LABELS[status]} strut</b>"
            "<br>ID %{customdata[1]}"
            "<br>midpoint XYZ (%{customdata[4]:.2f}, %{customdata[5]:.2f}, "
            "%{customdata[6]:.2f}) voxels"
            "<br>start XYZ (%{customdata[8]:.2f}, %{customdata[9]:.2f}, "
            "%{customdata[10]:.2f})"
            "<br>end XYZ (%{customdata[11]:.2f}, %{customdata[12]:.2f}, "
            "%{customdata[13]:.2f})"
            "<br>length %{customdata[7]:.2f} voxels"
            "<br>confidence %{customdata[3]:.2f}<extra></extra>"
        ),
        name=f"{STATUS_LABELS[status]} struts",
        showlegend=False,
    )


def _node_trace(
    records: list[dict[str, Any]],
    status: str,
    axis_order: str,
) -> go.Scatter3d:
    missing = status == "missing"
    positions = _reorder_xyz(
        [[record["x"], record["y"], record["z"]] for record in records],
        axis_order,
    )
    return go.Scatter3d(
        x=positions[:, 0],
        y=positions[:, 1],
        z=positions[:, 2],
        mode="markers",
        marker={
            "size": 6.5 if missing else 2.2,
            "symbol": "diamond-open" if missing else "circle",
            "color": STATUS_COLORS[status],
            "opacity": 1.0 if missing else 0.48,
            "line": {
                "width": 2 if missing else 0,
                "color": STATUS_COLORS[status],
            },
        },
        customdata=[
            [
                "node",
                record["id"],
                status,
                record.get("confidence", 1.0),
                record["x"],
                record["y"],
                record["z"],
            ]
            for record in records
        ],
        hovertemplate=(
            f"<b>{STATUS_LABELS[status]} node</b>"
            "<br>ID %{customdata[1]}"
            "<br>XYZ (%{customdata[4]:.2f}, %{customdata[5]:.2f}, "
            "%{customdata[6]:.2f}) voxels"
            "<br>confidence %{customdata[3]:.2f}<extra></extra>"
        ),
        name=f"{STATUS_LABELS[status]} nodes",
        showlegend=False,
    )


def _clicked_element(
    analysis: dict[str, Any],
    click_data: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    if not click_data:
        return None
    custom = click_data.get("points", [{}])[0].get("customdata")
    if not custom or len(custom) < 2 or custom[0] not in {"strut", "node"}:
        return None
    kind, identifier = custom[0], str(custom[1])
    collection = analysis["struts"] if kind == "strut" else analysis["nodes"]
    item = next(
        (record for record in collection if str(record["id"]) == identifier),
        None,
    )
    return (kind, item) if item is not None else None


def _selection_highlight(
    selected: tuple[str, dict[str, Any]] | None,
    axis_order: str,
) -> go.Scatter3d | None:
    if selected is None:
        return None
    kind, item = selected
    if kind == "strut":
        points = _reorder_xyz(item["polyline"], axis_order)
        return go.Scatter3d(
            x=points[:, 0],
            y=points[:, 1],
            z=points[:, 2],
            mode="lines",
            line={"color": "#ffffff", "width": 9},
            opacity=0.9,
            hoverinfo="skip",
            showlegend=False,
        )
    point = _reorder_xyz([item["x"], item["y"], item["z"]], axis_order)
    return go.Scatter3d(
        x=[point[0]],
        y=[point[1]],
        z=[point[2]],
        mode="markers",
        marker={
            "size": 12,
            "symbol": "diamond-open",
            "color": "#ffffff",
            "line": {"width": 3, "color": "#ffffff"},
        },
        hoverinfo="skip",
        showlegend=False,
    )


def _inspection_figure(
    dataset_key: str,
    analysis: dict[str, Any],
    statuses: list[str],
    elements: list[str],
    show_ct: bool,
    selected: tuple[str, dict[str, Any]] | None,
    axis_order: str = "XYZ",
    axis_maxima: dict[str, float | None] | None = None,
) -> go.Figure:
    allowed = set(statuses or [])
    element_types = set(elements or [])
    figure = go.Figure()
    normalized_axis_order = str(axis_order).upper()
    _axis_indices(normalized_axis_order)
    display_ranges = _display_axis_ranges(normalized_axis_order, axis_maxima)
    axis_upper = _axis_upper_bounds(axis_maxima)
    bounded_struts = (
        [
            record
            for record in analysis["struts"]
            if _record_intersects_bounds(record, "strut", axis_upper)
        ]
        if "struts" in element_types
        else []
    )
    bounded_nodes = (
        [
            record
            for record in analysis["nodes"]
            if _record_intersects_bounds(record, "node", axis_upper)
        ]
        if "nodes" in element_types
        else []
    )

    if show_ct:
        geometry = analysis.get("_display_geometry")
        if geometry is None:
            geometry = _display_geometry(
                dataset_key,
                str(analysis["meta"]["cache_fingerprint"]),
            )
        vertices = _reorder_xyz(
            geometry["surface_vertices_xyz"],
            normalized_axis_order,
        )
        faces = geometry["surface_faces"]
        figure.add_trace(
            go.Mesh3d(
                x=vertices[:, 0],
                y=vertices[:, 1],
                z=vertices[:, 2],
                i=faces[:, 0],
                j=faces[:, 1],
                k=faces[:, 2],
                color="#d6e4ea",
                opacity=0.10,
                flatshading=True,
                hoverinfo="skip",
                name="CT segmentation",
                showlegend=False,
            )
        )

    for status in STATUS_ORDER:
        if status not in allowed:
            continue
        if "struts" in element_types:
            struts = [
                record for record in bounded_struts
                if record["status"] == status
            ]
            if struts:
                figure.add_trace(
                    _strut_trace(struts, status, normalized_axis_order)
                )
        if "nodes" in element_types:
            nodes = [
                record for record in bounded_nodes
                if record["status"] == status
            ]
            if nodes:
                figure.add_trace(
                    _node_trace(nodes, status, normalized_axis_order)
                )

    if selected is not None:
        kind, item = selected
        element_key = "struts" if kind == "strut" else "nodes"
        if (
            item["status"] in allowed
            and element_key in element_types
            and _record_intersects_bounds(item, kind, axis_upper)
        ):
            highlight = _selection_highlight(selected, normalized_axis_order)
            if highlight is not None:
                figure.add_trace(highlight)

    figure.update_layout(
        height=760,
        paper_bgcolor="#071018",
        plot_bgcolor="#071018",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        hoverlabel={
            "bgcolor": "#10232f",
            "bordercolor": "#35505f",
            "font": {"color": "#f5fbff", "size": 12},
        },
        scene={
            "aspectmode": "data",
            "bgcolor": "#071018",
            "camera": {"eye": {"x": 1.45, "y": 1.45, "z": 1.1}},
            "xaxis": {
                "title": normalized_axis_order[0],
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[0],
            },
            "yaxis": {
                "title": normalized_axis_order[1],
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[1],
            },
            "zaxis": {
                "title": (
                    "Z / slice"
                    if normalized_axis_order[2] == "Z"
                    else normalized_axis_order[2]
                ),
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[2],
            },
        },
        # Keep the user's orbit/zoom while filters update.
        uirevision=(
            f"{dataset_key}:{analysis['meta']['cache_fingerprint']}:"
            f"{normalized_axis_order}:{display_ranges}"
        ),
    )
    return figure


def _visible_summary(
    analysis: dict[str, Any],
    statuses: list[str],
    elements: list[str],
    axis_maxima: dict[str, float | None] | None = None,
) -> list[Any]:
    allowed = set(statuses or [])
    element_types = set(elements or [])
    axis_upper = _axis_upper_bounds(axis_maxima)
    visible_struts = [
        record
        for record in analysis["struts"]
        if _record_intersects_bounds(record, "strut", axis_upper)
    ]
    visible_nodes = [
        record
        for record in analysis["nodes"]
        if _record_intersects_bounds(record, "node", axis_upper)
    ]
    n_struts = (
        sum(record["status"] in allowed for record in visible_struts)
        if "struts" in element_types
        else 0
    )
    n_nodes = (
        sum(record["status"] in allowed for record in visible_nodes)
        if "nodes" in element_types
        else 0
    )
    missing_struts = sum(
        record["status"] == "missing" for record in visible_struts
    )
    missing_nodes = sum(
        record["status"] == "missing" for record in visible_nodes
    )
    summary = [
        html.Span(f"{n_struts:,} struts · {n_nodes:,} nodes visible"),
        html.Span("•", className="summary-dot"),
        html.Span(
            f"{missing_struts:,} missing struts · {missing_nodes:,} missing nodes detected",
            className="missing-summary",
        ),
    ]
    for status in FILTER_ORDER[1:]:
        status_struts = sum(
            record["status"] == status for record in visible_struts
        )
        status_nodes = sum(
            record["status"] == status for record in visible_nodes
        )
        summary.extend(
            [
                html.Span("•", className="summary-dot"),
                html.Span(
                    f"{status_struts:,} {STATUS_LABELS[status].lower()} struts · "
                    f"{status_nodes:,} {STATUS_LABELS[status].lower()} nodes",
                    className=f"status-count status-count-{status}",
                ),
            ]
        )
    flagged_statuses = set(FILTER_ORDER[:-1])
    total_flagged = sum(
        record["status"] in flagged_statuses
        for record in visible_struts
    ) + sum(
        record["status"] in flagged_statuses
        for record in visible_nodes
    )
    summary.extend(
        [
            html.Span("•", className="summary-dot"),
            html.Span(
                f"{total_flagged:,} total flagged elements",
                className="total-flagged-summary",
            ),
        ]
    )
    validation = analysis.get("validation")
    if validation:
        strut_metrics = validation["struts"]
        summary.extend(
            [
                html.Span("•", className="summary-dot"),
                html.Span(
                    f"CAD validation: {strut_metrics['true_positive']}/"
                    f"{strut_metrics['expected']} intentional struts matched · "
                    f"F1 {100 * float(strut_metrics['f1']):.1f}%",
                    className="validation-summary",
                ),
            ]
        )
    return summary


def _selection_details(
    selected: tuple[str, dict[str, Any]] | None,
) -> list[Any]:
    if selected is None:
        return [
            html.Span("Click a strut or node to inspect it.", className="selection-hint"),
            html.Span(
                "Drag to orbit · scroll to zoom · double-click to reset",
                className="interaction-hint",
            ),
        ]

    kind, item = selected
    status = item["status"]
    details: list[Any] = [
        html.Span(
            f"{STATUS_LABELS.get(status, status.title())} {kind}",
            className=f"selection-status status-{status}",
        ),
        html.Strong(f"ID {item['id']}"),
        html.Span(f"confidence {float(item.get('confidence', 1.0)):.2f}"),
    ]
    if kind == "strut":
        geometry = _strut_geometry(item)
        details.extend(
            [
                html.Span(f"midpoint XYZ {_format_xyz(geometry['midpoint'])} voxels"),
                html.Span(f"start XYZ {_format_xyz(geometry['start'])}"),
                html.Span(f"end XYZ {_format_xyz(geometry['end'])}"),
                html.Span(f"length {geometry['length']:.2f} voxels"),
            ]
        )
        details.append(
            html.Span(f"present {100 * float(item.get('present_fraction', 0)):.1f}%")
        )
        measured = item.get("measured_thickness_um")
        design = item.get("design_thickness_um")
        if measured is not None:
            details.append(html.Span(f"measured {float(measured):.0f} μm"))
        if design is not None:
            details.append(html.Span(f"design {float(design):.0f} μm"))
    else:
        details.append(
            html.Span(
                f"XYZ {_format_xyz([item['x'], item['y'], item['z']])} voxels"
            )
        )
        details.append(html.Span(f"design degree {item.get('degree', '—')}"))
    if item.get("boundary_reason"):
        details.append(
            html.Span("scan boundary / registration mismatch")
        )
    return details


def _filter_options() -> list[dict[str, Any]]:
    return [
        {
            "label": html.Span(
                [
                    html.I(
                        className="filter-swatch",
                        style={"backgroundColor": STATUS_COLORS[status]},
                    ),
                    STATUS_LABELS[status],
                ],
                className="filter-label",
            ),
            "value": status,
        }
        for status in FILTER_ORDER
    ]


def create_app(default_dataset: str = "missing_struts") -> Dash:
    app = Dash(__name__, title="Registered Lattice Defect Map")
    config = get_dataset(default_dataset)
    volume_name = Path(config["volume"]).name
    design_name = Path(config["design"]).name

    app.layout = html.Main(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.Div("LLNL DSSI 2026 · CT / DESIGN COMPARISON", className="eyebrow"),
                            html.H1("Registered lattice defect map"),
                            html.P(
                                "Expected JSON geometry classified against the segmented TIFF volume.",
                                className="subtitle",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.B("TIFF"), html.Span(volume_name)],
                                className="source-file",
                            ),
                            html.Div(
                                [html.B("JSON"), html.Span(design_name)],
                                className="source-file",
                            ),
                        ],
                        className="source-files",
                    ),
                ],
                className="model-header",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Status", className="toolbar-label"),
                                    dcc.Checklist(
                                        id="status-filters",
                                        options=_filter_options(),
                                        value=list(FILTER_ORDER),
                                        inline=True,
                                        className="status-filters",
                                    ),
                                ],
                                className="filter-group",
                            ),
                            html.Div(
                                [
                                    html.Span("Elements", className="toolbar-label"),
                                    dcc.Checklist(
                                        id="element-filters",
                                        options=[
                                            {"label": "Struts", "value": "struts"},
                                            {"label": "Nodes", "value": "nodes"},
                                        ],
                                        value=["struts", "nodes"],
                                        inline=True,
                                        className="element-filters",
                                    ),
                                    dcc.Checklist(
                                        id="show-ct",
                                        options=[{"label": "CT surface", "value": "surface"}],
                                        value=["surface"],
                                        inline=True,
                                        className="element-filters ct-toggle",
                                    ),
                                ],
                                className="filter-group secondary-filters",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Threshold",
                                        htmlFor="threshold-control",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        [
                                            dcc.Input(
                                                id="threshold-control",
                                                type="number",
                                                value=None,
                                                debounce=True,
                                                placeholder="Auto (Otsu)",
                                                step="any",
                                                className="threshold-input",
                                            ),
                                            html.Button(
                                                "Auto",
                                                id="threshold-auto",
                                                type="button",
                                                className="control-button",
                                                title="Restore automatic Otsu thresholding",
                                            ),
                                        ],
                                        className="threshold-controls",
                                    ),
                                    html.Span(
                                        "Enter a value, then press Enter. Clear for Otsu.",
                                        className="control-help",
                                    ),
                                ],
                                className="parameter-control",
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Axis maximum",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                [
                                                    html.Span("X"),
                                                    dcc.Input(
                                                        id="x-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                            html.Label(
                                                [
                                                    html.Span("Y"),
                                                    dcc.Input(
                                                        id="y-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                            html.Label(
                                                [
                                                    html.Span("Z"),
                                                    dcc.Input(
                                                        id="z-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                        ],
                                        className="axis-limit-controls",
                                    ),
                                    html.Span(
                                        "Limits the displayed region and defect counts. "
                                        "Clear a value for Auto.",
                                        className="control-help",
                                    ),
                                ],
                                className="parameter-control axis-limit-control",
                            ),
                        ],
                        className="model-toolbar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                id="visible-summary",
                                className="visible-summary-content",
                            ),
                            html.Span(
                                id="threshold-readout",
                                className="threshold-readout",
                            ),
                        ],
                        className="visible-summary",
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#55d6be",
                        children=dcc.Graph(
                            id="viewer",
                            figure=_empty_figure("Preparing registered TIFF / JSON comparison…"),
                            config={
                                "displaylogo": False,
                                "scrollZoom": True,
                                "responsive": True,
                            },
                        ),
                    ),
                    html.Div(id="selection-details", className="selection-details"),
                ],
                className="model-panel",
            ),
        ],
        className="shell",
    )

    @app.callback(
        Output("viewer", "figure"),
        Output("visible-summary", "children"),
        Output("selection-details", "children"),
        Output("threshold-readout", "children"),
        Input("status-filters", "value"),
        Input("element-filters", "value"),
        Input("show-ct", "value"),
        Input("viewer", "clickData"),
        Input("threshold-control", "value"),
        Input("x-axis-max", "value"),
        Input("y-axis-max", "value"),
        Input("z-axis-max", "value"),
    )
    def update_model(
        statuses: list[str],
        elements: list[str],
        show_ct: list[str],
        click_data: dict[str, Any] | None,
        threshold_value: float | None,
        x_axis_max: float | None,
        y_axis_max: float | None,
        z_axis_max: float | None,
    ) -> tuple[Any, ...]:
        try:
            threshold = (
                None if threshold_value is None else float(threshold_value)
            )
            analysis = _analysis(
                default_dataset,
                float(config["voxel_size_mm"]),
                threshold,
            )
            selected = _clicked_element(analysis, click_data)
            active_threshold = float(analysis["meta"]["threshold"])
            threshold_source = analysis["meta"]["threshold_source"]
            source_label = (
                "automatic Otsu"
                if threshold_source in {"otsu", "sampled_otsu"}
                else "manual"
            )
            axis_maxima = {
                "X": x_axis_max,
                "Y": y_axis_max,
                "Z": z_axis_max,
            }
            return (
                _inspection_figure(
                    default_dataset,
                    analysis,
                    statuses or [],
                    elements or [],
                    "surface" in (show_ct or []),
                    selected,
                    "XYZ",
                    axis_maxima,
                ),
                _visible_summary(
                    analysis,
                    statuses or [],
                    elements or [],
                    axis_maxima,
                ),
                _selection_details(selected),
                f"Threshold {active_threshold:g} · {source_label}",
            )
        except Exception as exc:
            message = f"Could not load registered comparison: {exc}"
            return (
                _empty_figure(message),
                html.Span(message, className="error-message"),
                [html.Span(message, className="error-message")],
                "Threshold unavailable",
            )

    @app.callback(
        Output("threshold-control", "value"),
        Input("threshold-auto", "n_clicks"),
        prevent_initial_call=True,
    )
    def restore_automatic_threshold(_clicks: int | None) -> None:
        return None

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, default="missing_struts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--preprocess-only", action="store_true")
    args = parser.parse_args()
    if args.preprocess_only:
        analysis = ensure_analysis(args.dataset, get_dataset(args.dataset))
        print(
            f"Cached {args.dataset}: {len(analysis['defects']):,} candidate defects "
            f"in {analysis['_cache']['directory']}"
        )
        return
    viewer_app = create_app(args.dataset)
    print(f"Registered lattice defect map: http://{args.host}:{args.port}")
    viewer_app.run(host=args.host, port=args.port, debug=False)


app = create_app()
server = app.server

if __name__ == "__main__":
    main()
