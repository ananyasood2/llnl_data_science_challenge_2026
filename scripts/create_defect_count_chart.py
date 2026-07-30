"""Create poster-ready defect-classification count charts."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FixedLocator


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = REPO_ROOT / "data/missing_struts/processed/analysis.json"
OUTPUT_DIR = REPO_ROOT / "outputs/poster"

CATEGORIES = [
    "missing",
    "disconnected",
    "thick",
    "thin",
    "uncertain",
    "healthy",
]
COLORS = {
    "missing": "#E45756",
    "disconnected": "#2A9D8F",
    "thick": "#F4A261",
    "thin": "#8F63B8",
    "uncertain": "#4C78A8",
    "healthy": "#59A14F",
}


def main() -> None:
    analysis = json.loads(ANALYSIS_PATH.read_text())
    counts = Counter(
        str(record["status"])
        for element_type in ("struts", "nodes")
        for record in analysis[element_type]
    )
    values = [counts.get(category, 0) for category in CATEGORIES]

    figure, axis = plt.subplots(figsize=(12, 7.2), facecolor="white")
    bars = axis.barh(
        CATEGORIES,
        values,
        color=[COLORS[category] for category in CATEGORIES],
        height=0.66,
    )
    axis.invert_yaxis()
    axis.set_xscale("symlog", linthresh=10)
    axis.set_xlim(0, 40_000)
    axis.xaxis.set_major_locator(
        FixedLocator([0, 10, 100, 1_000, 10_000, 40_000])
    )
    axis.xaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _position: (
                f"{int(value / 1_000)}k" if value >= 1_000 else f"{int(value)}"
            )
        )
    )

    for bar, value in zip(bars, values, strict=True):
        axis.annotate(
            f"{value:,}",
            xy=(value, bar.get_y() + bar.get_height() / 2),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=13,
            fontweight="bold",
            color="#23313A",
        )

    axis.set_title(
        "Lattice Elements by Detector Classification",
        loc="left",
        fontsize=23,
        fontweight="bold",
        color="#17242C",
        pad=24,
    )
    axis.text(
        0,
        1.015,
        "Combined counts for registered struts and nodes",
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=13,
        color="#536773",
    )
    axis.set_xlabel(
        "Number of elements (symmetric logarithmic scale)",
        fontsize=13,
        labelpad=14,
        color="#334A56",
    )
    axis.tick_params(axis="x", labelsize=11, colors="#526A76")
    axis.tick_params(axis="y", labelsize=14, length=0, pad=12, colors="#23313A")
    axis.grid(axis="x", color="#DCE4E8", linewidth=0.9)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_visible(False)

    figure.text(
        0.985,
        0.018,
        "Source: data/missing_struts/processed/analysis.json",
        ha="right",
        va="bottom",
        fontsize=9,
        color="#71838C",
    )
    figure.tight_layout(rect=(0.04, 0.06, 0.98, 0.94))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        OUTPUT_DIR / "defect-category-counts.png",
        dpi=300,
        bbox_inches="tight",
        facecolor="white",
    )
    figure.savefig(
        OUTPUT_DIR / "defect-category-counts.svg",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)


if __name__ == "__main__":
    main()
