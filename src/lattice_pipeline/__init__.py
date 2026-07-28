"""CT lattice inspection data pipeline.

Coordinates exposed by this package are always ordered ``(x, y, z)``.  NumPy
volumes retain their conventional array order ``(z, y, x)``.
"""

from .align import AlignmentTransform, bbox_match_alignment, resolve_alignment
from .io import inspect_tiff_metadata, load_design_graph, load_volume

__all__ = [
    "AlignmentTransform",
    "bbox_match_alignment",
    "inspect_tiff_metadata",
    "load_design_graph",
    "load_volume",
    "resolve_alignment",
]
