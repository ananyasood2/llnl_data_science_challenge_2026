"""Dataset locations and physical defaults for the inspection dashboard."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "unitcell": {
        "label": "Unit cell · clean baseline",
        "volume": REPO_ROOT / "data/unitcell/unitcell.npy",
        "design": REPO_ROOT / "data/unitcell/polyhedron_1x1x1.json",
        "alignment_source": "bbox_match",
        "voxel_size_mm": 0.0252,
        "voxel_size_source": "estimated_from_4.56mm_unit_cell",
        "physical_span_mm": 4.56,
        "analysis_stride": 1,
    },
    "missing_struts": {
        "label": "9×9×9 · registered missing-strut scan",
        "volume": REPO_ROOT
        / "data/missing_struts/tif_stacks/"
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif",
        "design": REPO_ROOT
        / "data/missing_struts/registered_jsons/"
        "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json",
        "alignment_source": "registered_json",
        "nominal_design": REPO_ROOT / "data/missing_struts/octet_truss_9x9x9.json",
        "baseline_stl": REPO_ROOT / "data/missing_struts/stls/0.stl",
        "defect_stl": REPO_ROOT / "data/missing_struts/stls/0.5.stl",
        # Proper cube rotation mapping the 0.5% CAD orientation onto the
        # registered CT graph: x'=18-x, y'=18-z, z'=18-y.
        "cad_to_graph_symmetry": (
            -1.0, 0.0, 0.0,
            0.0, 0.0, -1.0,
            0.0, -1.0, 0.0,
        ),
        "cad_physical_span_mm": 9 * 4.56,
        # No physical TIFF resolution tags are present.  Nine 4.56 mm cells
        # span ~715 registered voxels in each axis.
        "voxel_size_mm": 0.057738,
        "voxel_size_source": "estimated_from_9x4.56mm_design_span",
        "physical_span_mm": 9 * 4.56,
        # Skeleton/EDT at half resolution keeps first-time processing practical.
        "analysis_stride": 2,
    },
}


def get_dataset(key: str) -> dict:
    """Return a copy of a dataset config or raise a friendly error."""
    if key not in DATASETS:
        raise ValueError(f"Unknown dataset {key!r}. Choose from: {', '.join(DATASETS)}")
    config = dict(DATASETS[key])
    missing = [str(config[name]) for name in ("volume", "design") if not config[name].is_file()]
    if missing:
        raise FileNotFoundError(
            "Dataset files are unavailable. If this is an LFS dataset, run "
            f"`git lfs pull`. Missing: {', '.join(missing)}"
        )
    return config
