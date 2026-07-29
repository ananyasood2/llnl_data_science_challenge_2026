"""Intensity-based segmentation for CT lattice volumes.

No normalization is assumed: Otsu's method is evaluated on the finite values in
the volume's native intensity range.  The threshold can be supplied explicitly
by the UI or a caller higher in the processing pipeline.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from skimage.filters import threshold_otsu

Foreground = Literal["bright", "dark"]


def _validate_volume(volume: np.ndarray) -> np.ndarray:
    array = np.asanyarray(volume)
    if array.ndim != 3:
        raise ValueError(f"Expected a 3-D CT volume, got shape {array.shape!r}")
    if not np.issubdtype(array.dtype, np.number):
        raise TypeError(f"Expected numeric CT intensities, got {array.dtype}")
    if array.size == 0:
        raise ValueError("Cannot segment an empty volume")
    return array


def otsu_threshold(volume: np.ndarray) -> float:
    """Return an Otsu threshold in the volume's native intensity units.

    Non-finite pixels are ignored.  A constant finite volume has an unambiguous
    threshold (that constant value), which avoids warnings from histogram code.
    """

    array = _validate_volume(volume)
    # Integer CT scans are finite by construction.  Keeping the original array
    # here is important for the ~1 GiB registered TIFF, which is memory-mappable;
    # boolean indexing would otherwise create another full-size intensity copy.
    if np.issubdtype(array.dtype, np.inexact):
        finite_mask = np.isfinite(array)
        if not np.any(finite_mask):
            raise ValueError("Cannot threshold a volume containing no finite values")
        values = array if np.all(finite_mask) else np.asarray(array[finite_mask])
    else:
        values = array
    value_min = np.min(values)
    value_max = np.max(values)
    if value_min == value_max:
        return float(value_min)
    return float(threshold_otsu(values))


def segment_volume(
    volume: np.ndarray,
    threshold: float | None = None,
    *,
    foreground: Foreground = "bright",
) -> np.ndarray:
    """Segment a 3-D CT volume and return a boolean material mask.

    Parameters
    ----------
    threshold:
        Native-intensity threshold.  If omitted, it is computed with Otsu.
    foreground:
        ``"bright"`` for the usual high-density CT material or ``"dark"`` for
        inverted scans.  Non-finite voxels are always background.
    """

    array = _validate_volume(volume)
    if foreground not in ("bright", "dark"):
        raise ValueError("foreground must be either 'bright' or 'dark'")
    used_threshold = otsu_threshold(array) if threshold is None else float(threshold)
    if not np.isfinite(used_threshold):
        raise ValueError("threshold must be finite")

    finite: np.ndarray | bool
    finite = (
        np.isfinite(array)
        if np.issubdtype(array.dtype, np.inexact)
        else True
    )
    if foreground == "bright":
        return np.asarray(finite & (array > used_threshold), dtype=bool)
    return np.asarray(finite & (array < used_threshold), dtype=bool)


def segment_with_metadata(
    volume: np.ndarray,
    threshold: float | None = None,
    *,
    foreground: Foreground = "bright",
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return the material mask and a JSON-serializable segmentation summary."""

    array = _validate_volume(volume)
    used_threshold = otsu_threshold(array) if threshold is None else float(threshold)
    mask = segment_volume(array, used_threshold, foreground=foreground)
    foreground_voxels = int(np.count_nonzero(mask))
    return mask, {
        "threshold": used_threshold,
        "threshold_source": "otsu" if threshold is None else "user_override",
        "foreground": foreground,
        "foreground_voxels": foreground_voxels,
        "foreground_fraction": float(foreground_voxels / mask.size),
    }


# A short alias is convenient for pipeline callers.
segment = segment_with_metadata
