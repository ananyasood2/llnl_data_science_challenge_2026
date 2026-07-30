"""FastMCP entry point for safe, dataset-scoped lattice analysis tools.

Run with ``python -m app.copilot.mcp_server`` after the analysis service has
access to the registered datasets.  Unlike the legacy MCP server, no tool
accepts client-controlled filesystem paths.
"""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from .tools import (
    analyze_connectivity_in_bounds,
    compare_expected_geometry_with_ct,
    create_viewport_nde_report,
    generate_ct_evidence_slices,
    get_current_viewport_context,
    identify_disconnected_components,
    inspect_selected_element,
    list_visible_elements,
    summarize_visible_defects,
)

mcp = FastMCP("Lattice CT Copilot")


@mcp.tool()
def get_viewport_context(context_id: str) -> dict:
    return get_current_viewport_context(context_id)


@mcp.tool()
def list_visible_struts_and_nodes(
    context_id: str,
    kinds: list[Literal["strut", "node"]] | None = None,
    cursor: int = 0,
    limit: int = 100,
) -> dict:
    return list_visible_elements(context_id, kinds, cursor, limit)


@mcp.tool()
def analyze_connectivity(context_id: str) -> dict:
    return analyze_connectivity_in_bounds(context_id)


@mcp.tool()
def get_disconnected_components(context_id: str) -> dict:
    return identify_disconnected_components(context_id)


@mcp.tool()
def inspect_element(
    context_id: str,
    kind: Literal["strut", "node"] | None = None,
    element_id: int | str | None = None,
) -> dict:
    return inspect_selected_element(context_id, kind, element_id)


@mcp.tool()
def generate_ct_evidence(context_id: str) -> dict:
    return generate_ct_evidence_slices(context_id)


@mcp.tool()
def compare_expected_geometry(context_id: str) -> dict:
    return compare_expected_geometry_with_ct(context_id)


@mcp.tool()
def summarize_defects(context_id: str) -> dict:
    return summarize_visible_defects(context_id)


@mcp.tool()
def create_nde_report(context_id: str) -> dict:
    return create_viewport_nde_report(context_id)


if __name__ == "__main__":
    mcp.run()
