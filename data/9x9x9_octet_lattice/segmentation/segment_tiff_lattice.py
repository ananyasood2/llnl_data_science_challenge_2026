"""Bounded closed-loop TIFF segmentation used by the Task 6 subagent."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import matplotlib
import numpy as np
import tifffile
from skimage.filters import threshold_otsu

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def choose_threshold(source: Path, output: Path, max_iterations: int = 10, max_failed: int = 3) -> tuple[float, list[dict[str, float | int]]]:
    with tifffile.TiffFile(source) as tif:
        index = min(380, len(tif.pages) - 1)
        image = tif.pages[index].asarray()
    baseline = float(threshold_otsu(image))
    candidates = [baseline * factor for factor in (0.80, 0.90, 1.00, 1.10, 1.20)]
    diagnostics: list[dict[str, float | int]] = []
    best_score, best_threshold, failed = float("-inf"), baseline, 0
    figure, axes = plt.subplots(1, len(candidates) + 1, figsize=(4 * (len(candidates) + 1), 4), constrained_layout=True)
    axes[0].imshow(image, cmap="gray")
    axes[0].set_title(f"Raw slice {index}")
    axes[0].axis("off")
    for iteration, (threshold, axis) in enumerate(zip(candidates, axes[1:]), start=1):
        if iteration > max_iterations or failed >= max_failed:
            break
        mask = image >= threshold
        fraction = float(mask.mean())
        score = 1.0 - abs(fraction - 0.15) / 0.15 if 0.01 <= fraction <= 0.45 else -1.0
        diagnostics.append({"iteration": iteration, "threshold": float(threshold), "foreground_fraction": fraction, "score": score})
        axis.imshow(mask, cmap="gray")
        axis.set_title(f"{iteration}: t={threshold:.0f}\nfg={fraction:.1%}")
        axis.axis("off")
        if score > best_score:
            best_score, best_threshold, failed = score, threshold, 0
        else:
            failed += 1
    output.mkdir(parents=True, exist_ok=True)
    figure.savefig(output / "threshold_iterations.png", dpi=150)
    plt.close(figure)
    return float(best_threshold), diagnostics


def segment_stack(source: Path, output: Path, threshold: float) -> tuple[int, int, tuple[int, ...]]:
    foreground, total, shape = 0, 0, ()
    with tifffile.TiffFile(source) as tif, tifffile.TiffWriter(output, bigtiff=True) as writer:
        for page in tif.pages:
            mask = (page.asarray() >= threshold).astype(np.uint8)
            writer.write(mask, photometric="minisblack", compression="deflate")
            foreground += int(mask.sum())
            total += mask.size
            shape = (len(tif.pages), *mask.shape)
    return foreground, total, shape


def run(source: Path, max_iterations: int = 10, max_failed: int = 3) -> Path:
    source = source.resolve()
    destination = source.parent / "segmentation"
    threshold, iterations = choose_threshold(source, destination, max_iterations, max_failed)
    mask_path = destination / "segmented_mask.tif"
    foreground, total, shape = segment_stack(source, mask_path, threshold)
    slice_index = min(380, shape[0] - 1)
    with tifffile.TiffFile(mask_path) as tif:
        mask_slice = tif.pages[slice_index].asarray()
    plt.imsave(destination / f"slice_{slice_index}.png", mask_slice, cmap="gray")
    shutil.copy2(Path(__file__), destination / "segment_tiff_lattice.py")
    (destination / "iterations.json").write_text(json.dumps(iterations, indent=2), encoding="utf-8")
    (destination / "segmentation_report.md").write_text(
        "# Segmentation Subagent Report\n\n"
        f"- Input: `{source}`\n- Output mask: `{mask_path.name}`\n- Mask shape: `{shape}`\n"
        f"- Selected threshold: `{threshold:.6g}`\n- Foreground voxels: `{foreground}`\n"
        f"- Background voxels: `{total - foreground}`\n- Foreground fraction: `{foreground / total:.4%}`\n"
        f"- Iterations evaluated: `{len(iterations)}` (limit: {max_iterations}; failed-attempt limit: {max_failed})\n\n"
        "## Evidence\n\n- `threshold_iterations.png` records the closed-loop candidates and slice-level feedback.\n"
        f"- `slice_{slice_index}.png` is the required final mask view.\n"
        "- `iterations.json` and `segment_tiff_lattice.py` provide reproducibility.\n",
        encoding="utf-8",
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment a lattice TIFF into a traceable output folder.")
    parser.add_argument("input_tiff", type=Path)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--max-failed", type=int, default=3)
    args = parser.parse_args()
    print(run(args.input_tiff, args.max_iterations, args.max_failed))


if __name__ == "__main__":
    main()
