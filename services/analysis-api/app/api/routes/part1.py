"""Read-only Part 1 evidence endpoints for the interactive dashboard."""

from __future__ import annotations

import csv
import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image, ImageDraw
from skimage.measure import marching_cubes
import tifffile

router = APIRouter(prefix="/api/v1/part1", tags=["part1"])
_ROOT = Path(__file__).resolve().parents[5]


@lru_cache
def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        raw = np.load(_ROOT / "data" / "unitcell" / "unitcell.npy", mmap_mode="r")
        mask = np.load(_ROOT / "output" / "part1" / "unitcell_mask.npy", mmap_mode="r")
        skeleton = np.load(_ROOT / "output" / "part1" / "unitcell_skeleton.npy", mmap_mode="r")
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail="Part 1 volume artifacts are not available.") from error
    if raw.shape != mask.shape or raw.shape != skeleton.shape:
        raise HTTPException(status_code=503, detail="Part 1 evidence arrays have incompatible shapes.")
    return raw, mask, skeleton


@lru_cache
def _score() -> dict:
    path = _ROOT / "evals" / "evaluation_segmentation_1.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/summary")
def summary() -> dict:
    raw, mask, skeleton = _arrays()
    score = _score()
    return {
        "score": score["score"],
        "comment": score["reasoning"],
        "shape": list(raw.shape),
        "foreground_voxels": int(np.count_nonzero(mask)),
        "skeleton_voxels": int(np.count_nonzero(skeleton)),
        "threshold": 0.005813,
    }


@lru_cache
def _mesh() -> dict:
    """Create a bounded, browser-ready isosurface and skeleton point cloud."""
    _, mask, skeleton = _arrays()
    factor = 4
    # Max pooling preserves thin lattice material in the reduced live view.
    reduced = np.asarray(mask, dtype=np.uint8).reshape(64, factor, 64, factor, 64, factor).max(axis=(1, 3, 5))
    vertices, faces, _, _ = marching_cubes(reduced, level=0.5)
    points = np.argwhere(np.asarray(skeleton)[::factor, ::factor, ::factor])
    # XYZ browser coordinates, centered around the volume origin.
    verts = (vertices[:, ::-1] - 31.5).astype(np.float32)
    skeleton_points = (points[:, ::-1] - 31.5).astype(np.float32)
    return {"vertices": verts.round(3).tolist(), "faces": faces.astype(np.uint32).tolist(), "skeleton": skeleton_points.round(3).tolist(), "downsample": factor}


@router.get("/mesh")
def mesh() -> dict:
    return _mesh()


@router.get("/slice.png")
def slice_image(z: int = Query(default=128, ge=0, le=255)) -> Response:
    raw, mask, skeleton = _arrays()
    plane = np.asarray(raw[z], dtype=np.float32)
    low, high = np.percentile(plane, (1, 99.5))
    normalized = np.clip((plane - low) / max(high - low, 1e-9), 0, 1)
    rgb = np.repeat((normalized * 255).astype(np.uint8)[..., None], 3, axis=2)
    rgb[mask[z].astype(bool)] = (74, 174, 145)
    rgb[skeleton[z].astype(bool)] = (239, 154, 55)
    image = Image.fromarray(rgb, mode="RGB")
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return Response(content=stream.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/xray-neighborhood.png")
def xray_neighborhood(x: float = Query(...), y: float = Query(...), z: float = Query(...)) -> Response:
    """Return a labeled CT neighborhood for a selected registered strut point."""
    source = _ROOT / "data" / "missing_struts" / "tif_stacks" / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
    with tifffile.TiffFile(source) as tif:
        zi = max(0, min(len(tif.pages) - 1, round(z)))
        image = tif.pages[zi].asarray()
    xi, yi, radius = round(x), round(y), 52
    crop = image[max(0, yi - radius): yi + radius, max(0, xi - radius): xi + radius].astype(np.float32)
    low, high = np.percentile(crop, (1, 99.5)); gray = np.clip((crop - low) / max(high - low, 1e-9), 0, 1)
    rendered = Image.fromarray((gray * 255).astype(np.uint8), mode="L").convert("RGB")
    draw = ImageDraw.Draw(rendered); cx, cy = xi - max(0, xi - radius), yi - max(0, yi - radius)
    draw.line((cx - 12, cy, cx + 12, cy), fill=(239, 144, 39), width=2); draw.line((cx, cy - 12, cx, cy + 12), fill=(239, 144, 39), width=2)
    stream = io.BytesIO(); rendered.save(stream, format="PNG", optimize=True)
    return Response(content=stream.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})
