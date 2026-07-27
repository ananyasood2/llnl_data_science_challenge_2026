"""Shared local CT evidence generation for registered lattice struts.

This module intentionally contains no MCP or FastAPI code.  It is used by
both the MCP tool and the dashboard API so they produce identical local ROI
artifacts and apply the same coordinate convention.
"""

import json
from pathlib import Path

import numpy as np
import tifffile


def _save_roi_overlay(
    raw_plane: np.ndarray,
    mask_plane: np.ndarray,
    output_path: Path,
    title: str,
    x_label: str,
    y_label: str,
    display_limits: tuple[float, float],
) -> None:
    """Save one raw-CT plane with a transparent red segmentation overlay."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    figure, axis = plt.subplots(figsize=(7, 6), constrained_layout=True)
    axis.imshow(
        raw_plane,
        cmap="gray",
        vmin=display_limits[0],
        vmax=display_limits[1],
        origin="lower",
    )
    foreground = np.ma.masked_where(~mask_plane.astype(bool), mask_plane)
    axis.imshow(
        foreground,
        cmap=ListedColormap(["#ff3b30"]),
        alpha=0.48,
        interpolation="nearest",
        origin="lower",
    )
    axis.set_title(title)
    axis.set_xlabel(x_label)
    axis.set_ylabel(y_label)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def analyze_strut_roi_service(
    strut_id: int,
    json_filepath: str | Path,
    mask_filepath: str | Path,
    raw_tiff_filepath: str | Path,
    defects_filepath: str | Path,
    output_directory: str | Path,
    margin_voxels: int = 20,
) -> dict:
    """Create local raw-CT and mask evidence for one registered lattice strut.

    Registered JSON coordinates are XYZ; raw CT and mask array indexing is
    ZYX.  Both inputs are memory mapped and only the endpoint-bounded crop is
    materialized in memory.
    """
    blueprint_path = Path(json_filepath)
    mask_path = Path(mask_filepath)
    raw_tiff_path = Path(raw_tiff_filepath)
    defects_path = Path(defects_filepath)
    output_root = Path(output_directory)

    for label, path in (
        ("Registered JSON", blueprint_path),
        ("Segmented mask", mask_path),
        ("Raw TIFF", raw_tiff_path),
        ("Defect results", defects_path),
    ):
        if not path.is_file():
            return {"status": "error", "message": f"{label} not found: {path}"}
    if margin_voxels < 0:
        return {"status": "error", "message": "margin_voxels must be non-negative."}
    if output_root.exists() and not output_root.is_dir():
        return {
            "status": "error",
            "message": f"output_directory must be a directory path: {output_root}",
        }

    try:
        with blueprint_path.open("r", encoding="utf-8") as file:
            blueprint = json.load(file)
        junctions = {
            junction["id"]: np.asarray(junction["position"], dtype=float)
            for junction in blueprint.get("junctions", [])
        }
        strut = next(
            (entry for entry in blueprint.get("struts", []) if entry.get("id") == strut_id),
            None,
        )
        if strut is None:
            return {"status": "error", "message": f"Unknown registered strut ID: {strut_id}"}

        try:
            endpoint0_xyz = junctions[strut["junction0"]]
            endpoint1_xyz = junctions[strut["junction1"]]
        except KeyError:
            return {
                "status": "error",
                "message": f"Strut {strut_id} references a junction absent from the registered JSON.",
            }

        mask_volume = np.load(mask_path, mmap_mode="r")
        raw_volume = tifffile.memmap(raw_tiff_path)
        if mask_volume.ndim != 3 or raw_volume.ndim != 3:
            return {
                "status": "error",
                "message": (
                    "Raw TIFF and segmented mask must both be 3D; "
                    f"received {raw_volume.shape} and {mask_volume.shape}."
                ),
            }
        if tuple(raw_volume.shape) != tuple(mask_volume.shape):
            return {
                "status": "error",
                "message": (
                    "Raw TIFF and segmented mask shapes must match; "
                    f"received {raw_volume.shape} and {mask_volume.shape}."
                ),
            }

        endpoint0_zyx = np.rint(endpoint0_xyz[[2, 1, 0]]).astype(int)
        endpoint1_zyx = np.rint(endpoint1_xyz[[2, 1, 0]]).astype(int)
        volume_shape = np.asarray(mask_volume.shape, dtype=int)
        roi_start_zyx = np.maximum(
            np.floor(np.minimum(endpoint0_zyx, endpoint1_zyx)).astype(int) - margin_voxels,
            0,
        )
        roi_stop_zyx = np.minimum(
            np.ceil(np.maximum(endpoint0_zyx, endpoint1_zyx)).astype(int) + margin_voxels + 1,
            volume_shape,
        )
        if np.any(roi_start_zyx >= roi_stop_zyx):
            return {
                "status": "error",
                "message": f"Strut {strut_id} does not produce a valid in-bounds ROI.",
            }

        roi_slices = tuple(
            slice(int(start), int(stop)) for start, stop in zip(roi_start_zyx, roi_stop_zyx)
        )
        raw_roi = np.asarray(raw_volume[roi_slices]).copy()
        mask_roi = np.asarray(mask_volume[roi_slices]).astype(bool, copy=True)
        midpoint_zyx = np.rint((endpoint0_zyx + endpoint1_zyx) / 2).astype(int)
        midpoint_zyx = np.clip(midpoint_zyx, roi_start_zyx, roi_stop_zyx - 1)
        midpoint_local_zyx = midpoint_zyx - roi_start_zyx

        try:
            with defects_path.open("r", encoding="utf-8") as file:
                defects_data = json.load(file)
            global_evidence = next(
                (
                    score
                    for score in defects_data.get("strut_scores", [])
                    if score.get("strut_id") == strut_id
                ),
                None,
            )
            calibration_warning = defects_data.get("analysis_parameters", {}).get(
                "calibration_warning"
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            global_evidence = None
            calibration_warning = f"Unable to read defects.json evidence: {error}"

        finite_values = raw_roi[np.isfinite(raw_roi)]
        if finite_values.size:
            display_min, display_max = np.percentile(finite_values, [1, 99])
            if display_min == display_max:
                display_min = float(finite_values.min())
                display_max = float(finite_values.max())
        else:
            display_min, display_max = 0.0, 1.0
        if display_min == display_max:
            display_max = display_min + 1.0
        display_limits = (float(display_min), float(display_max))

        artifact_directory = output_root / f"strut_{strut_id}"
        artifact_directory.mkdir(parents=True, exist_ok=True)
        raw_roi_path = artifact_directory / "raw_roi.npy"
        mask_roi_path = artifact_directory / "mask_roi.npy"
        metadata_path = artifact_directory / "roi_metadata.json"
        xy_path = artifact_directory / "roi_xy.png"
        xz_path = artifact_directory / "roi_xz.png"
        yz_path = artifact_directory / "roi_yz.png"

        np.save(raw_roi_path, raw_roi)
        np.save(mask_roi_path, mask_roi)

        local_z, local_y, local_x = (int(value) for value in midpoint_local_zyx)
        _save_roi_overlay(
            raw_roi[local_z, :, :], mask_roi[local_z, :, :], xy_path,
            f"Strut {strut_id}: XY at global Z={midpoint_zyx[0]}", "X voxel", "Y voxel",
            display_limits,
        )
        _save_roi_overlay(
            raw_roi[:, local_y, :], mask_roi[:, local_y, :], xz_path,
            f"Strut {strut_id}: XZ at global Y={midpoint_zyx[1]}", "X voxel", "Z voxel",
            display_limits,
        )
        _save_roi_overlay(
            raw_roi[:, :, local_x], mask_roi[:, :, local_x], yz_path,
            f"Strut {strut_id}: YZ at global X={midpoint_zyx[2]}", "Y voxel", "Z voxel",
            display_limits,
        )

        artifact_paths = {
            "raw_roi": str(raw_roi_path),
            "mask_roi": str(mask_roi_path),
            "metadata": str(metadata_path),
            "xy_overlay": str(xy_path),
            "xz_overlay": str(xz_path),
            "yz_overlay": str(yz_path),
        }
        metadata = {
            "strut_id": strut_id,
            "coordinate_convention": "registered JSON XYZ -> volume ZYX",
            "endpoint0_xyz": endpoint0_xyz.tolist(),
            "endpoint1_xyz": endpoint1_xyz.tolist(),
            "endpoint0_zyx": endpoint0_zyx.tolist(),
            "endpoint1_zyx": endpoint1_zyx.tolist(),
            "roi_start_zyx": roi_start_zyx.tolist(),
            "roi_stop_zyx_exclusive": roi_stop_zyx.tolist(),
            "roi_shape_zyx": list(raw_roi.shape),
            "midpoint_zyx": midpoint_zyx.tolist(),
            "midpoint_local_zyx": midpoint_local_zyx.tolist(),
            "margin_voxels": margin_voxels,
            "raw_display_limits": list(display_limits),
            "global_evidence": global_evidence,
            "calibration_warning": calibration_warning,
            "artifacts": artifact_paths,
        }
        with metadata_path.open("w", encoding="utf-8") as file:
            json.dump(metadata, file, indent=2)

        return {
            "status": "success",
            "message": f"Saved local CT and segmentation evidence for strut {strut_id}.",
            "strut_id": strut_id,
            "classification": global_evidence.get("classification") if global_evidence else "unavailable",
            "global_evidence": global_evidence,
            "roi": {
                "coordinate_convention": "registered JSON XYZ -> volume ZYX",
                "endpoint0_xyz": endpoint0_xyz.tolist(),
                "endpoint1_xyz": endpoint1_xyz.tolist(),
                "roi_start_zyx": roi_start_zyx.tolist(),
                "roi_stop_zyx_exclusive": roi_stop_zyx.tolist(),
                "shape_zyx": list(raw_roi.shape),
                "midpoint_zyx": midpoint_zyx.tolist(),
            },
            "calibration_warning": calibration_warning,
            "artifacts": artifact_paths,
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return {"status": "error", "message": f"Error analyzing strut ROI: {error}"}
