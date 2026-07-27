from __future__ import annotations

import io
import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = ROOT / "data" / "9x9x9_octet_lattice"
OUTPUT_DIR = DATASET_DIR / "segmentation"
os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from PIL import Image
from skimage.metrics import structural_similarity as ssim

INPUT_TIF = Path(os.environ.get("SEG_INPUT_TIF", "/private/tmp/9x9x9_octet_lattice.tif"))
GROUND_TRUTH_PNG = DATASET_DIR / "ground_truth_segmentation_slice_380.png"
MASK_TIF = DATASET_DIR / "9x9x9_octet_lattice_segmentation_threshold_39000.tif"
SLICE_PNG = OUTPUT_DIR / "segmentation_slice_380.png"
COMPARISON_PNG = OUTPUT_DIR / "slice_380_comparison.png"
THRESHOLD_SWEEP_PNG = OUTPUT_DIR / "threshold_sweep_slice_380.png"
THRESHOLD_SWEEP_JSON = OUTPUT_DIR / "threshold_sweep_results.json"
REPORT_MD = OUTPUT_DIR / "SEGMENTATION_REPORT.md"
SLICE_INDEX = 380
AXIS = 0
THRESHOLDS = [33000, 36000, 39000, 42000, 45000, 48000, 51000, 54000, 56000]


@dataclass
class ThresholdResult:
    threshold: int
    rendered_ssim: float
    plot_area_foreground_iou: float
    plot_area_foreground_f1: float
    slice_foreground_voxels: int


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / ".matplotlib").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / ".matplotlib"))


def render_mask(mask: np.ndarray, output_path: Path | None = None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    image = ax.imshow(mask, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
    ax.set_title(f"Slice {SLICE_INDEX} along axis {AXIS}")
    colorbar = fig.colorbar(image)
    colorbar.set_ticks(np.linspace(0.0, 1.0, 6))
    fig.canvas.draw()

    renderer = fig.canvas.get_renderer()
    bbox = ax.get_window_extent(renderer=renderer).transformed(fig.dpi_scale_trans.inverted())
    left = int(round(bbox.x0 * fig.dpi))
    right = int(round(bbox.x1 * fig.dpi))
    top = int(round((fig.get_figheight() - bbox.y1) * fig.dpi))
    bottom = int(round((fig.get_figheight() - bbox.y0) * fig.dpi))

    if output_path is not None:
        fig.savefig(output_path)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    buffer.seek(0)
    rendered = np.array(Image.open(buffer).convert("RGB"))
    return rendered, (left, top, right, bottom)


def compute_binary_metrics(gt_crop: np.ndarray, pred_crop: np.ndarray) -> dict[str, float]:
    viridis = plt.get_cmap("viridis")
    background = np.array(viridis(0.0)[:3]) * 255.0
    foreground = np.array(viridis(1.0)[:3]) * 255.0

    def classify(rgb: np.ndarray) -> np.ndarray:
        rgb_float = rgb.astype(np.float32)
        dist_bg = np.sum((rgb_float - background) ** 2, axis=2)
        dist_fg = np.sum((rgb_float - foreground) ** 2, axis=2)
        return dist_fg < dist_bg

    gt_mask = classify(gt_crop)
    pred_mask = classify(pred_crop)

    tp = int(np.logical_and(gt_mask, pred_mask).sum())
    fp = int(np.logical_and(~gt_mask, pred_mask).sum())
    fn = int(np.logical_and(gt_mask, ~pred_mask).sum())
    tn = int(np.logical_and(~gt_mask, ~pred_mask).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) else 0.0

    return {
        "plot_area_foreground_iou": iou,
        "plot_area_foreground_f1": f1,
        "plot_area_foreground_precision": precision,
        "plot_area_foreground_recall": recall,
        "plot_area_accuracy": accuracy,
        "plot_area_tp": tp,
        "plot_area_fp": fp,
        "plot_area_fn": fn,
        "plot_area_tn": tn,
    }


def choose_threshold(slice_data: np.ndarray, gt_image: np.ndarray) -> tuple[ThresholdResult, list[ThresholdResult], np.ndarray, tuple[int, int, int, int]]:
    best: ThresholdResult | None = None
    all_results: list[ThresholdResult] = []
    best_render: np.ndarray | None = None
    best_bbox: tuple[int, int, int, int] | None = None

    for threshold in THRESHOLDS:
        mask = (slice_data >= threshold).astype(np.uint8)
        rendered, bbox = render_mask(mask)
        left, top, right, bottom = bbox
        gt_crop = gt_image[top:bottom, left:right]
        pred_crop = rendered[top:bottom, left:right]
        area_metrics = compute_binary_metrics(gt_crop, pred_crop)
        score = float(ssim(gt_image, rendered, channel_axis=2))
        result = ThresholdResult(
            threshold=threshold,
            rendered_ssim=score,
            plot_area_foreground_iou=float(area_metrics["plot_area_foreground_iou"]),
            plot_area_foreground_f1=float(area_metrics["plot_area_foreground_f1"]),
            slice_foreground_voxels=int(mask.sum()),
        )
        all_results.append(result)

        is_better = False
        if best is None:
            is_better = True
        elif result.plot_area_foreground_iou > best.plot_area_foreground_iou:
            is_better = True
        elif (
            math.isclose(result.plot_area_foreground_iou, best.plot_area_foreground_iou)
            and result.plot_area_foreground_f1 > best.plot_area_foreground_f1
        ):
            is_better = True
        elif (
            math.isclose(result.plot_area_foreground_iou, best.plot_area_foreground_iou)
            and math.isclose(result.plot_area_foreground_f1, best.plot_area_foreground_f1)
            and result.rendered_ssim > best.rendered_ssim
        ):
            is_better = True

        if is_better:
            best = result
            best_render = rendered
            best_bbox = bbox

    assert best is not None
    assert best_render is not None
    assert best_bbox is not None
    return best, all_results, best_render, best_bbox


def save_threshold_plot(results: list[ThresholdResult]) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=100)
    thresholds = [row.threshold for row in results]
    scores = [row.rendered_ssim for row in results]
    ax.plot(thresholds, scores, marker="o", linewidth=2, color="#0b7285")
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Rendered-image SSIM")
    ax.set_title("Slice 380 threshold search")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(THRESHOLD_SWEEP_PNG)
    plt.close(fig)


def save_comparison(gt_image: np.ndarray, pred_image: np.ndarray, bbox: tuple[int, int, int, int]) -> dict[str, float]:
    left, top, right, bottom = bbox
    gt_crop = gt_image[top:bottom, left:right]
    pred_crop = pred_image[top:bottom, left:right]

    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=100)
    axes[0].imshow(gt_image)
    axes[0].set_title("Ground truth")
    axes[0].axis("off")
    axes[1].imshow(pred_image)
    axes[1].set_title("Predicted segmentation")
    axes[1].axis("off")
    fig.tight_layout()
    fig.savefig(COMPARISON_PNG)
    plt.close(fig)

    mse = float(np.mean((gt_image.astype(np.float32) - pred_image.astype(np.float32)) ** 2))
    mae = float(np.mean(np.abs(gt_image.astype(np.float32) - pred_image.astype(np.float32))))

    metrics = {
        "rendered_ssim": float(ssim(gt_image, pred_image, channel_axis=2)),
        "rendered_mse": mse,
        "rendered_mae": mae,
    }
    metrics.update(compute_binary_metrics(gt_crop, pred_crop))
    return metrics


def segment_volume(volume: np.memmap, threshold: int) -> tuple[int, int]:
    foreground = 0
    background = 0

    with tifffile.TiffWriter(MASK_TIF, bigtiff=True) as writer:
        for index in range(volume.shape[0]):
            mask = (volume[index] >= threshold).astype(np.uint8)
            fg = int(mask.sum())
            foreground += fg
            background += mask.size - fg
            writer.write(mask, photometric="minisblack", contiguous=True)

    return foreground, background


def write_report(
    shape: tuple[int, ...],
    dtype: str,
    best: ThresholdResult,
    results: list[ThresholdResult],
    foreground: int,
    background: int,
    metrics: dict[str, float],
) -> None:
    total_voxels = foreground + background
    volume_fraction = foreground / total_voxels if total_voxels else 0.0

    lines = [
        "# Segmentation Report",
        "",
        f"- date: 2026-07-21",
        f"- input volume: `{INPUT_TIF}`",
        f"- ground truth image: `{GROUND_TRUTH_PNG.relative_to(ROOT)}`",
        f"- volume shape: `{shape}`",
        f"- volume dtype: `{dtype}`",
        f"- selected threshold: `{best.threshold}`",
        f"- slice index: `{SLICE_INDEX}`",
        f"- axis: `{AXIS}`",
        f"- foreground voxels: `{foreground}`",
        f"- background voxels: `{background}`",
        f"- foreground fraction: `{volume_fraction:.6%}`",
        "",
        "## Threshold Search",
        "",
        "| threshold | rendered SSIM | plot-area IoU | plot-area F1 | slice foreground voxels |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(
            f"| {row.threshold} | {row.rendered_ssim:.6f} | {row.plot_area_foreground_iou:.6f} | {row.plot_area_foreground_f1:.6f} | {row.slice_foreground_voxels} |"
        )

    lines.extend(
        [
            "",
            "## Validation Against `ground_truth_segmentation_slice_380.png`",
            "",
            f"- rendered SSIM: `{metrics['rendered_ssim']:.6f}`",
            f"- rendered MSE: `{metrics['rendered_mse']:.6f}`",
            f"- rendered MAE: `{metrics['rendered_mae']:.6f}`",
            f"- plot-area foreground IoU: `{metrics['plot_area_foreground_iou']:.6f}`",
            f"- plot-area foreground F1: `{metrics['plot_area_foreground_f1']:.6f}`",
            f"- plot-area precision: `{metrics['plot_area_foreground_precision']:.6f}`",
            f"- plot-area recall: `{metrics['plot_area_foreground_recall']:.6f}`",
            f"- plot-area accuracy: `{metrics['plot_area_accuracy']:.6f}`",
            "",
            "## Outputs",
            "",
            f"- mask TIFF: `{MASK_TIF.relative_to(ROOT)}`",
            f"- slice visualization: `{SLICE_PNG.relative_to(ROOT)}`",
            f"- comparison image: `{COMPARISON_PNG.relative_to(ROOT)}`",
            f"- threshold sweep plot: `{THRESHOLD_SWEEP_PNG.relative_to(ROOT)}`",
            f"- threshold sweep JSON: `{THRESHOLD_SWEEP_JSON.relative_to(ROOT)}`",
            f"- report: `{REPORT_MD.relative_to(ROOT)}`",
            "",
            "## Notes",
            "",
            "- The optimization loop evaluated 9 thresholds and selected the best one by plot-area foreground IoU on slice 380, using plot-area F1 and rendered-image SSIM as tie-breakers.",
            "- Validation is image-based because the provided reference is a rendered PNG rather than a voxel-aligned mask volume.",
        ]
    )

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_dirs()
    volume = tifffile.memmap(INPUT_TIF)
    gt_image = np.array(Image.open(GROUND_TRUTH_PNG).convert("RGB"))
    slice_data = np.take(volume, SLICE_INDEX, axis=AXIS)

    best, results, best_render, bbox = choose_threshold(slice_data, gt_image)
    final_mask = (slice_data >= best.threshold).astype(np.uint8)
    render_mask(final_mask, output_path=SLICE_PNG)
    save_threshold_plot(results)

    THRESHOLD_SWEEP_JSON.write_text(
        json.dumps([asdict(row) for row in results], indent=2),
        encoding="utf-8",
    )

    metrics = save_comparison(gt_image, best_render, bbox)
    foreground, background = segment_volume(volume, best.threshold)

    write_report(
        shape=tuple(int(v) for v in volume.shape),
        dtype=str(volume.dtype),
        best=best,
        results=results,
        foreground=foreground,
        background=background,
        metrics=metrics,
    )

    summary = {
        "selected_threshold": best.threshold,
        "slice_rendered_ssim": best.rendered_ssim,
        "foreground_voxels": foreground,
        "background_voxels": background,
        "outputs": {
            "mask_tif": str(MASK_TIF),
            "slice_png": str(SLICE_PNG),
            "comparison_png": str(COMPARISON_PNG),
            "threshold_sweep_png": str(THRESHOLD_SWEEP_PNG),
            "threshold_sweep_json": str(THRESHOLD_SWEEP_JSON),
            "report_md": str(REPORT_MD),
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
