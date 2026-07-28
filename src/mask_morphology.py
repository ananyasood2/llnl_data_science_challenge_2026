"""Conservative, reproducible preprocessing for binary CT segmentation masks."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_closing


MORPHOLOGY_OPERATION = "binary_closing"
MORPHOLOGY_LIBRARY = "scipy.ndimage.binary_closing"
MORPHOLOGY_VERSION = 1
STRUCTURE_SHAPE = (3, 3, 3)
ITERATIONS = 1
BORDER_VALUE = 0


def closing_structure() -> np.ndarray:
    """Return the conservative one-voxel-radius cubic closing kernel."""

    return np.ones(STRUCTURE_SHAPE, dtype=bool)


def close_binary_mask(mask: np.ndarray) -> np.ndarray:
    """Fill small 3D segmentation holes without changing the input in place.

    The zero border value treats voxels outside the acquired CT volume as air.
    """

    binary_mask = np.asarray(mask, dtype=bool)
    if binary_mask.ndim != 3:
        raise ValueError(f"Expected a 3D binary mask; found shape {binary_mask.shape}.")

    # scipy's finite-volume operation would otherwise erode foreground that
    # touches the acquired volume boundary. Padding by the kernel radius gives
    # the same result as closing in an infinite air background, then crops back
    # to the acquired CT extent.
    pad_width = tuple((size // 2, size // 2) for size in STRUCTURE_SHAPE)
    padded_mask = np.pad(binary_mask, pad_width, mode="constant", constant_values=False)
    closed_padded = binary_closing(
        padded_mask,
        structure=closing_structure(),
        iterations=ITERATIONS,
        border_value=BORDER_VALUE,
    )
    crop = tuple(slice(before, before + size) for (before, _), size in zip(pad_width, binary_mask.shape))
    return np.asarray(
        closed_padded[crop],
        dtype=bool,
    )
