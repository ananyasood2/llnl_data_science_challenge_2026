"""Create a compact CT / segmentation / connectivity-flag comparison figure."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from skimage.measure import label


def create_figure(volume_path: Path, mask_path: Path, skeleton_path: Path, output_path: Path, slice_index: int) -> Path:
    volume = np.load(volume_path)
    mask = np.load(mask_path) > 0
    skeleton = np.load(skeleton_path) > 0
    if volume.shape != mask.shape or mask.shape != skeleton.shape:
        raise ValueError("Volume, mask, and skeleton must have identical shapes.")
    if not 0 <= slice_index < volume.shape[0]:
        raise IndexError(f"Slice index {slice_index} is outside 0..{volume.shape[0] - 1}.")

    component_count = int(label(skeleton, connectivity=3).max())
    flagged = max(component_count - 1, 0)
    raw_slice, mask_slice, skeleton_slice = volume[slice_index], mask[slice_index], skeleton[slice_index]

    figure, axes = plt.subplots(1, 3, figsize=(15, 5.4), constrained_layout=True)
    figure.suptitle(f"Unit-cell CT inspection comparison — axial slice {slice_index}", fontsize=16, fontweight="bold")

    axes[0].imshow(raw_slice, cmap="gray")
    axes[0].set_title("CT slice\nRaw X-ray attenuation")

    axes[1].imshow(mask_slice, cmap="gray", vmin=0, vmax=1)
    axes[1].set_title("Segmentation\nOtsu threshold = 0.005813")

    axes[2].imshow(raw_slice, cmap="gray")
    axes[2].imshow(np.ma.masked_where(~mask_slice, mask_slice), cmap="Blues", alpha=0.34, vmin=0, vmax=1)
    axes[2].imshow(np.ma.masked_where(~skeleton_slice, skeleton_slice), cmap="autumn", alpha=0.95, vmin=0, vmax=1)
    status = "No disconnected components flagged" if flagged == 0 else f"{flagged} disconnected component(s) flagged"
    axes[2].set_title(f"Connectivity flag detection\n{status}")

    for axis in axes:
        axis.set_axis_off()
    axes[2].text(
        0.02,
        0.02,
        f"Skeleton components: {component_count}\nForeground: {mask.mean():.2%}",
        transform=axes[2].transAxes,
        color="white",
        fontsize=10,
        va="bottom",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "black", "alpha": 0.7, "edgecolor": "none"},
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volume", type=Path, default=Path("data/unitcell/unitcell.npy"))
    parser.add_argument("--mask", type=Path, default=Path("output/part1/unitcell_mask.npy"))
    parser.add_argument("--skeleton", type=Path, default=Path("output/part1/unitcell_skeleton.npy"))
    parser.add_argument("--output", type=Path, default=Path("output/part1/ct_segmentation_flag_comparison.png"))
    parser.add_argument("--slice", type=int, default=128)
    args = parser.parse_args()
    print(create_figure(args.volume, args.mask, args.skeleton, args.output, args.slice))


if __name__ == "__main__":
    main()
