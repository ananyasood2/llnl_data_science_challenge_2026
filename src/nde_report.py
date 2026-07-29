"""Generate the Task 4 NDE Markdown report from a volume, mask, and skeleton."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from skimage.measure import label


def _load_visualizer():
    script = Path(__file__).parents[1] / ".agents" / "skills" / "nde_report_expert" / "scripts" / "3d_visualize.py"
    spec = importlib.util.spec_from_file_location("nde_visualizer", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load visualizer: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_report(volume_path: Path, mask_path: Path, skeleton_path: Path, output_directory: Path) -> Path:
    volume, mask, skeleton = (np.load(path) for path in (volume_path, mask_path, skeleton_path))
    if volume.shape != mask.shape or mask.shape != skeleton.shape:
        raise ValueError(f"Incompatible shapes: volume={volume.shape}, mask={mask.shape}, skeleton={skeleton.shape}")
    output_directory.mkdir(parents=True, exist_ok=True)
    visualizer = _load_visualizer()
    view_a, view_b = output_directory / "view_a.png", output_directory / "view_b.png"
    visualizer.visualize_3d_with_skeleton(str(mask_path), str(skeleton_path), str(view_a), threshold=0.5, downsample_factor=4, elev=30.0, azim=45.0)
    visualizer.visualize_3d_with_skeleton(str(mask_path), str(skeleton_path), str(view_b), threshold=0.5, downsample_factor=4, elev=60.0, azim=45.0)
    foreground = mask > 0
    skeleton_foreground = skeleton > 0
    components = int(label(skeleton_foreground, connectivity=3).max())
    report = output_directory / "nde_report.md"
    report.write_text(
        "# Non-Destructive Evaluation Report\n\n"
        "## Inputs\n\n"
        f"- Volume: `{volume_path}`\n- Mask: `{mask_path}`\n- Skeleton: `{skeleton_path}`\n\n"
        "## Summary\n\n"
        "| Metric | Value |\n| --- | ---: |\n"
        f"| Volume shape | `{volume.shape}` |\n"
        f"| Raw mean intensity | {float(volume.mean()):.6g} |\n"
        f"| Foreground voxel count | {int(foreground.sum())} |\n"
        f"| Foreground fraction | {float(foreground.mean()):.4%} |\n"
        f"| Skeleton voxel count | {int(skeleton_foreground.sum())} |\n"
        f"| Skeleton connected components | {components} |\n\n"
        "## Visual gallery\n\n"
        "### View A - elevation 30, azimuth 45\n\n![View A](view_a.png)\n\n"
        "### View B - elevation 60, azimuth 45\n\n![View B](view_b.png)\n\n"
        "## Interpretation\n\n"
        "The mask and skeleton have identical volume dimensions. The foreground fraction quantifies mask-to-volume coverage; skeleton voxels and connected components provide a compact connectivity proxy. Review both rendered views before treating a component count as a defect finding, because segmentation thresholding can split or merge struts.\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the Task 4 NDE report.")
    parser.add_argument("volume", type=Path)
    parser.add_argument("mask", type=Path)
    parser.add_argument("skeleton", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/nde_report"))
    args = parser.parse_args()
    print(f"Wrote {write_report(args.volume, args.mask, args.skeleton, args.output)}")


if __name__ == "__main__":
    main()
