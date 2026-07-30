"""CT lattice inspection data pipeline.

Coordinates exposed by this package are always ordered ``(x, y, z)``.  NumPy
volumes retain their conventional array order ``(z, y, x)``.
"""

from .align import AlignmentTransform, bbox_match_alignment, resolve_alignment
from .coordinates import (
    CoordinateTransform,
    json_strut_to_voxel_endpoints,
    json_xyz_to_physical_xyz,
    physical_xyz_to_voxel_zyx,
    voxel_zyx_to_physical_xyz,
)
from .io import inspect_tiff_metadata, load_design_graph, load_volume

__all__ = [
    "AlignmentTransform",
    "CoordinateTransform",
    "bbox_match_alignment",
    "inspect_tiff_metadata",
    "json_strut_to_voxel_endpoints",
    "json_xyz_to_physical_xyz",
    "load_design_graph",
    "load_volume",
    "physical_xyz_to_voxel_zyx",
    "resolve_alignment",
    "voxel_zyx_to_physical_xyz",
]
"""Shared deterministic lattice CT analysis package."""
