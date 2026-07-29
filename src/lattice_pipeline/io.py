"""Input helpers for CT volumes and lattice design graphs.

The public coordinate convention is ``(x, y, z)`` even though loaded volume
arrays are indexed as ``volume[z, y, x]``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import tifffile


_MM_PER_UNIT = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "um": 1e-3,
    "µm": 1e-3,
    "micron": 1e-3,
    "microns": 1e-3,
    "nm": 1e-6,
    "cm": 10.0,
    "inch": 25.4,
    "in": 25.4,
}


def _as_float(value: Any) -> float:
    """Convert TIFF rational/scalar values to a float."""
    if isinstance(value, tuple) and len(value) == 2:
        return float(value[0]) / float(value[1])
    return float(value)


def _resolution_unit_name(value: Any) -> str | None:
    name = getattr(value, "name", None)
    if name:
        return str(name).lower()
    # TIFF ResolutionUnit: 2=inches, 3=centimetres.
    return {2: "inch", 3: "cm"}.get(int(value)) if value is not None else None


def inspect_tiff_metadata(path: str | Path) -> dict[str, Any]:
    """Inspect a TIFF without reading its pixel payload.

    ``voxel_size_mm`` is returned in ``(x, y, z)`` order only when all three
    dimensions are recoverable. A two-value ``pixel_size_xy_mm`` is still
    reported when only the planar TIFF resolution tags are available.
    """
    path = Path(path)
    with tifffile.TiffFile(path) as tif:
        if not tif.series:
            raise ValueError(f"TIFF contains no image series: {path}")
        series = tif.series[0]
        page = tif.pages[0]
        tags = page.tags
        imagej_raw = dict(tif.imagej_metadata or {})
        # ImageJ stores one source filename per slice under ``Labels`` for this
        # dataset. Keep inspection metadata compact rather than duplicating 761
        # long filenames into every analysis cache.
        imagej = {
            key: value
            for key, value in imagej_raw.items()
            if key != "Labels"
        }
        if "Labels" in imagej_raw:
            imagej["label_count"] = len(imagej_raw["Labels"])

        x_size_mm = y_size_mm = z_size_mm = None
        resolution_unit = None
        if "ResolutionUnit" in tags:
            resolution_unit = _resolution_unit_name(tags["ResolutionUnit"].value)
        unit_mm = _MM_PER_UNIT.get(resolution_unit or "")
        if unit_mm and "XResolution" in tags and "YResolution" in tags:
            x_ppu = _as_float(tags["XResolution"].value)
            y_ppu = _as_float(tags["YResolution"].value)
            if x_ppu > 0 and y_ppu > 0:
                x_size_mm = unit_mm / x_ppu
                y_size_mm = unit_mm / y_ppu

        imagej_unit = str(imagej.get("unit", "")).lower()
        imagej_unit_mm = _MM_PER_UNIT.get(imagej_unit)
        if imagej_unit_mm and imagej.get("spacing") is not None:
            spacing = float(imagej["spacing"])
            if spacing > 0:
                z_size_mm = spacing * imagej_unit_mm

        voxel_size = None
        if all(v is not None for v in (x_size_mm, y_size_mm, z_size_mm)):
            voxel_size = [x_size_mm, y_size_mm, z_size_mm]

        selected_tags = {}
        for name in (
            "ImageWidth",
            "ImageLength",
            "BitsPerSample",
            "Compression",
            "PhotometricInterpretation",
            "XResolution",
            "YResolution",
            "ResolutionUnit",
            "ImageDescription",
            "Software",
        ):
            if name in tags:
                value = tags[name].value
                selected_tags[name] = getattr(value, "name", value)

        return {
            "path": str(path.resolve()),
            "shape_zyx": [int(v) for v in series.shape],
            "axes": series.axes,
            "dtype": str(series.dtype),
            "page_count": len(tif.pages),
            "is_imagej": bool(tif.is_imagej),
            "imagej_metadata": imagej,
            "tags": selected_tags,
            "pixel_size_xy_mm": (
                [x_size_mm, y_size_mm]
                if x_size_mm is not None and y_size_mm is not None
                else None
            ),
            "voxel_size_mm": voxel_size,
            "voxel_size_source": "tif_metadata" if voxel_size else None,
        }


def load_volume(path: str | Path, *, mmap: bool = True) -> np.ndarray:
    """Load a ``.npy`` or TIFF volume in array order ``(z, y, x)``.

    Memory mapping is used by default. A clear error is raised for an unpulled
    Git LFS pointer instead of passing its text to NumPy or tifffile.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CT volume not found: {path}")
    with path.open("rb") as stream:
        prefix = stream.read(128)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/"):
        raise RuntimeError(
            f"{path} is a Git LFS pointer, not image data. Run `git lfs pull` "
            "from the repository root and try again."
        )

    suffix = path.suffix.lower()
    if suffix == ".npy":
        volume = np.load(path, mmap_mode="r" if mmap else None, allow_pickle=False)
    elif suffix in {".tif", ".tiff"}:
        if mmap:
            try:
                volume = tifffile.memmap(path, mode="r")
            except (ValueError, OSError):
                volume = tifffile.imread(path)
        else:
            volume = tifffile.imread(path)
    else:
        raise ValueError(f"Unsupported CT volume format {suffix!r}: {path}")

    volume = np.asarray(volume) if not mmap else volume
    if volume.ndim != 3:
        raise ValueError(
            f"Expected a 3D CT volume in (z, y, x) order, got {volume.shape} "
            f"from {path}"
        )
    return volume


def load_design_graph(path: str | Path) -> dict[str, Any]:
    """Load and validate the challenge ``junctions``/``struts`` JSON schema.

    Raw list fields are retained, while derived lookup and geometry fields are
    added for downstream processing. Junction positions are interpreted and
    exposed in the JSON's documented ``(x, y, z)`` order.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Design graph not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid design graph JSON {path}: {exc}") from exc

    junctions = raw.get("junctions")
    struts = raw.get("struts")
    if not isinstance(junctions, list) or not isinstance(struts, list):
        raise ValueError(
            f"Design graph {path} must contain list fields 'junctions' and 'struts'"
        )

    junction_by_id: dict[int, dict[str, Any]] = {}
    positions = []
    for junction in junctions:
        if "id" not in junction or "position" not in junction:
            raise ValueError(f"Junction missing id/position in {path}: {junction}")
        junction_id = int(junction["id"])
        position = np.asarray(junction["position"], dtype=float)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError(
                f"Junction {junction_id} has invalid xyz position: "
                f"{junction['position']}"
            )
        if junction_id in junction_by_id:
            raise ValueError(f"Duplicate junction id {junction_id} in {path}")
        junction_by_id[junction_id] = junction
        positions.append(position)

    strut_by_id: dict[int, dict[str, Any]] = {}
    degree_by_id = {junction_id: 0 for junction_id in junction_by_id}
    for strut in struts:
        missing = {"id", "junction0", "junction1"} - strut.keys()
        if missing:
            raise ValueError(f"Strut missing {sorted(missing)} in {path}: {strut}")
        strut_id = int(strut["id"])
        node_a = int(strut["junction0"])
        node_b = int(strut["junction1"])
        if node_a not in junction_by_id or node_b not in junction_by_id:
            raise ValueError(
                f"Strut {strut_id} references unknown junction(s) "
                f"{node_a}, {node_b} in {path}"
            )
        if strut_id in strut_by_id:
            raise ValueError(f"Duplicate strut id {strut_id} in {path}")
        strut_by_id[strut_id] = strut
        degree_by_id[node_a] += 1
        degree_by_id[node_b] += 1

    positions_xyz = np.asarray(positions, dtype=float).reshape((-1, 3))
    bbox = None
    if positions_xyz.size:
        bbox = {
            "min_xyz": positions_xyz.min(axis=0).tolist(),
            "max_xyz": positions_xyz.max(axis=0).tolist(),
        }

    return {
        "path": str(path.resolve()),
        "junctions": junctions,
        "struts": struts,
        "unit_cells": raw.get("unit_cells", []),
        "junction_by_id": junction_by_id,
        "strut_by_id": strut_by_id,
        "degree_by_id": degree_by_id,
        "positions_xyz": positions_xyz,
        "bbox_xyz": bbox,
        "raw_metadata": {
            key: value
            for key, value in raw.items()
            if key not in {"junctions", "struts", "unit_cells"}
        },
    }
