"""Reproducible segmentation for the 9x9x9 octet-lattice CT volume.

The threshold is supplied after evaluating percentile-based candidates.  The
script writes a binary TIFF mask and a central-slice quality-control image.
"""
from pathlib import Path
import argparse
import os

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".matplotlib"))
import matplotlib.pyplot as plt
import numpy as np
import tifffile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--input", type=Path, default=Path("../9x9x9_octet_lattice.tif"))
    parser.add_argument("--output", type=Path, default=Path("segmented_mask.tif"))
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    source = args.input if args.input.is_absolute() else (base / args.input).resolve()
    output = args.output if args.output.is_absolute() else base / args.output
    volume = tifffile.memmap(source)
    mask = volume >= args.threshold
    tifffile.imwrite(output, mask.astype(np.uint8), compression="deflate", metadata={"axes": "ZYX"})

    z = volume.shape[0] // 2
    fig, ax = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True)
    ax[0].imshow(volume[z], cmap="gray")
    ax[0].set_title(f"Raw CT, slice {z}")
    ax[1].imshow(volume[z], cmap="gray")
    ax[1].imshow(mask[z], cmap="autumn", alpha=0.42, interpolation="nearest")
    ax[1].set_title(f"Mask overlay (threshold={args.threshold:.1f})")
    for a in ax:
        a.axis("off")
    fig.savefig(base / "slice_overlay.png", dpi=200)

    n = mask.size
    fg = int(mask.sum())
    print(f"foreground_voxels={fg}")
    print(f"background_voxels={n - fg}")
    print(f"foreground_percentage={100 * fg / n:.4f}")


if __name__ == "__main__":
    main()
