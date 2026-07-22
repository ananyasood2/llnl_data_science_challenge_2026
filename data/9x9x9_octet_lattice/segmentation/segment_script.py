"""Reproducibly segment the 9x9x9 octet-lattice CT stack.

Run from any directory:
    python segment_script.py

The chosen threshold (41711) is the p90 intensity of the source stack, selected
after percentile-based candidate screening and slice-level visual comparison.
"""
from pathlib import Path
import os

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt
import numpy as np
import tifffile


THRESHOLD = 41711
SLICE_INDEX = 380


def main() -> None:
    output_dir = Path(__file__).resolve().parent
    source_path = output_dir.parent / "9x9x9_octet_lattice.tif"
    mask_path = output_dir / "mask.tif"
    slice_path = output_dir / "slice_380.png"

    volume = tifffile.memmap(source_path)
    if volume.ndim != 3:
        raise ValueError(f"Expected a 3D TIFF stack; got shape {volume.shape}.")
    if not 0 <= SLICE_INDEX < volume.shape[0]:
        raise ValueError(f"Slice {SLICE_INDEX} is outside the volume.")

    # uint8 values are exactly 0 (background) and 1 (foreground).
    mask = (volume >= THRESHOLD).astype(np.uint8)
    tifffile.imwrite(mask_path, mask, compression="deflate", metadata={"axes": "ZYX"})

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(mask[SLICE_INDEX], cmap="gray", vmin=0, vmax=1, interpolation="nearest")
    ax.set_title(f"Binary mask, slice {SLICE_INDEX} (threshold {THRESHOLD})")
    ax.set_axis_off()
    fig.tight_layout(pad=0)
    fig.savefig(slice_path, dpi=180, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    foreground = int(mask.sum())
    total = int(mask.size)
    print(f"threshold={THRESHOLD}")
    print(f"shape={mask.shape}")
    print(f"foreground_voxels={foreground}")
    print(f"background_voxels={total - foreground}")
    print(f"foreground_percent={100 * foreground / total:.6f}")


if __name__ == "__main__":
    main()
