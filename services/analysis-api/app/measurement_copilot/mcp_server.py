"""FastMCP exposure for qualified, dataset-scoped measurement tools."""

from __future__ import annotations

from fastmcp import FastMCP

from .tools import (
    analyze_measurement_sensitivity as _analyze_measurement_sensitivity,
    compare_measurements_to_design as _compare_measurements_to_design,
    create_measurement_report as _create_measurement_report,
    get_measurement_context as _get_measurement_context,
    get_relative_density as _get_relative_density,
    get_thickness_summary as _get_thickness_summary,
    list_out_of_spec_struts as _list_out_of_spec_struts,
)


mcp = FastMCP("Lattice Measurement Analysis")


@mcp.tool()
def get_measurement_context(context_id: str) -> dict:
    """Return the immutable targets and qualified analysis revision for a measurement context."""

    return _get_measurement_context(context_id)


@mcp.tool()
def get_thickness_summary(context_id: str) -> dict:
    """Return deterministic thickness statistics, histogram bins, eligibility, and warnings."""

    return _get_thickness_summary(context_id)


@mcp.tool()
def list_out_of_spec_struts(
    context_id: str,
    cutoff_um: float | None = None,
    limit: int = 10,
) -> dict:
    """Return a bounded, thinnest-first list of registered struts below a cutoff."""

    return _list_out_of_spec_struts(context_id, cutoff_um, limit)


@mcp.tool()
def get_relative_density(context_id: str) -> dict:
    """Return segmented volume, registered enclosing volume, relative density, and ROI provenance."""

    return _get_relative_density(context_id)


@mcp.tool()
def compare_measurements_to_design(context_id: str) -> dict:
    """Apply the explicit provisional policy to thickness and density results."""

    return _compare_measurements_to_design(context_id)


@mcp.tool()
def analyze_measurement_sensitivity(
    context_id: str,
    cutoffs_um: list[float] | None = None,
) -> dict:
    """Compare percent-below results for up to twenty thickness cutoffs without rerunning CT."""

    return _analyze_measurement_sensitivity(context_id, cutoffs_um)


@mcp.tool()
def create_measurement_report(context_id: str) -> dict:
    """Create immutable JSON and Markdown derivative reports from deterministic measurements."""

    return _create_measurement_report(context_id)


if __name__ == "__main__":
    mcp.run()
