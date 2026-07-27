import json
from pathlib import Path

import numpy as np
import tifffile
from fastmcp import FastMCP

try:
    from src.lattice_roi import analyze_strut_roi_service
except ModuleNotFoundError:  # Supports launching this file directly from src/.
    from lattice_roi import analyze_strut_roi_service

# Initialize the MCP server
mcp = FastMCP("CT Segmentation")

@mcp.tool()
def segment_ct_dataset(input_filepath: str, output_filepath: str, threshold: float) -> str:
    """
    Segments a 3D CT dataset based on a given density threshold value.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D CT scan data.
        output_filepath: Path indicating where the segmented .npy file should be saved.
        threshold: The density value to use as a threshold. Voxels >= threshold will be set to 1, others to 0.
    
    Returns:
        A status message indicating success and the save location, or an error message.
    """

    import numpy as np

    data = np.load(input_filepath)
    mask = (data >= threshold).astype(np.uint8)
    np.save(output_filepath, mask)
    return f"Saved segmentation to {output_filepath}"


@mcp.tool()
def segment_tiff_volume(
    input_filepath: str,
    output_filepath: str,
    raw_threshold: int = 41711,
) -> dict:
    """Segment a 3D TIFF CT volume with a raw intensity threshold.

    The TIFF is memory-mapped so the raw 3D volume is not copied into RAM before
    thresholding. The resulting boolean mask is stored as a ``.npy`` file, which
    later tools can reopen with ``mmap_mode='r'``.

    Args:
        input_filepath: Path to the raw 3D TIFF CT scan.
        output_filepath: Destination path for the boolean ``.npy`` mask.
        raw_threshold: Raw CT intensity at or above which a voxel is material.

    Returns:
        Structured status and mask metadata, or an error description.
    """
    source = Path(input_filepath)
    destination = Path(output_filepath)

    if not source.is_file():
        return {"status": "error", "message": f"Input TIFF not found: {source}"}
    if destination.suffix.lower() != ".npy":
        return {
            "status": "error",
            "message": "output_filepath must end with .npy for a NumPy mask.",
        }

    try:
        volume = tifffile.memmap(source)
        if volume.ndim != 3:
            return {
                "status": "error",
                "message": f"Expected a 3D TIFF volume; found shape {volume.shape}.",
            }

        destination.parent.mkdir(parents=True, exist_ok=True)
        mask = volume >= raw_threshold
        np.save(destination, mask)

        foreground_voxels = int(np.count_nonzero(mask))
        total_voxels = int(mask.size)
        return {
            "status": "success",
            "mask_filepath": str(destination),
            "shape": list(mask.shape),
            "dtype": str(mask.dtype),
            "raw_threshold": raw_threshold,
            "foreground_voxels": foreground_voxels,
            "foreground_percentage": round(100 * foreground_voxels / total_voxels, 6),
        }
    except Exception as error:
        return {"status": "error", "message": f"Error segmenting TIFF: {error}"}


def _neighborhood_contains_material(
    mask: np.ndarray, center: np.ndarray, radius: int
) -> bool:
    """Check whether an in-bounds cubic neighborhood contains foreground voxels."""
    lower = np.maximum(center - radius, 0)
    upper = np.minimum(center + radius + 1, np.asarray(mask.shape))
    if np.any(lower >= upper):
        return False
    return bool(mask[lower[0] : upper[0], lower[1] : upper[1], lower[2] : upper[2]].any())


@mcp.tool()
def validate_registered_alignment(
    json_filepath: str,
    mask_filepath: str,
    sample_count: int = 0,
    neighborhood_radius: int = 1,
) -> dict:
    """Validate how registered JSON coordinates index a segmented CT mask.

    Tests evenly distributed junctions with both likely conventions: JSON XYZ
    coordinates indexed as mask ZYX and as mask XYZ. Each test checks a small
    material neighborhood, making validation robust to fractional coordinates
    and minor registration residuals.

    Args:
        json_filepath: Path to the registered lattice JSON blueprint.
        mask_filepath: Path to the segmented boolean ``.npy`` mask.
        sample_count: Number of evenly distributed junctions to test. Use 0
            (the default) to test every registered junction.
        neighborhood_radius: Voxel radius for the material-neighborhood check.

    Returns:
        Candidate hit rates, a recommended index order, and whether the
        alignment is strong enough for downstream defect analysis.
    """
    blueprint_path = Path(json_filepath)
    mask_path = Path(mask_filepath)
    if not blueprint_path.is_file():
        return {"status": "error", "message": f"Registered JSON not found: {blueprint_path}"}
    if not mask_path.is_file():
        return {"status": "error", "message": f"Segmented mask not found: {mask_path}"}
    if sample_count < 0 or neighborhood_radius < 0:
        return {
            "status": "error",
            "message": "sample_count cannot be negative and neighborhood_radius cannot be negative.",
        }

    try:
        with blueprint_path.open("r", encoding="utf-8") as file:
            blueprint = json.load(file)
        junctions = blueprint.get("junctions", [])
        if not junctions:
            return {"status": "error", "message": "The registered JSON contains no junctions."}

        mask = np.load(mask_path, mmap_mode="r")
        if mask.ndim != 3:
            return {
                "status": "error",
                "message": f"Expected a 3D mask; found shape {mask.shape}.",
            }

        selected_count = len(junctions) if sample_count == 0 else min(sample_count, len(junctions))
        selected_indices = np.linspace(0, len(junctions) - 1, num=selected_count, dtype=int)
        zyx_hits = 0
        xyz_hits = 0
        zyx_in_bounds = 0
        xyz_in_bounds = 0

        for index in selected_indices:
            coordinates = np.rint(junctions[index]["position"]).astype(int)
            xyz_index = coordinates
            zyx_index = coordinates[[2, 1, 0]]

            if np.all((zyx_index >= 0) & (zyx_index < np.asarray(mask.shape))):
                zyx_in_bounds += 1
                zyx_hits += _neighborhood_contains_material(mask, zyx_index, neighborhood_radius)
            if np.all((xyz_index >= 0) & (xyz_index < np.asarray(mask.shape))):
                xyz_in_bounds += 1
                xyz_hits += _neighborhood_contains_material(mask, xyz_index, neighborhood_radius)

        tested = len(selected_indices)
        zyx_hit_rate = zyx_hits / tested
        xyz_hit_rate = xyz_hits / tested
        strong_threshold = 0.8

        if zyx_hit_rate > xyz_hit_rate and zyx_hit_rate >= strong_threshold:
            recommendation = "zyx"
            is_valid = True
        elif xyz_hit_rate > zyx_hit_rate and xyz_hit_rate >= strong_threshold:
            recommendation = "xyz"
            is_valid = True
        else:
            recommendation = None
            is_valid = False

        return {
            "status": "success",
            "mask_shape": list(mask.shape),
            "sampled_junctions": tested,
            "neighborhood_radius": neighborhood_radius,
            "candidate_results": {
                "zyx": {
                    "material_hits": zyx_hits,
                    "in_bounds": zyx_in_bounds,
                    "hit_rate": round(zyx_hit_rate, 6),
                },
                "xyz": {
                    "material_hits": xyz_hits,
                    "in_bounds": xyz_in_bounds,
                    "hit_rate": round(xyz_hit_rate, 6),
                },
            },
            "recommended_index_order": recommendation,
            "is_valid": is_valid,
            "message": (
                "Alignment is suitable for strut evaluation."
                if is_valid
                else "Neither tested convention met the 80% material-hit threshold; verify registration before evaluating struts."
            ),
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return {"status": "error", "message": f"Error validating alignment: {error}"}


def _longest_low_material_gap_fraction(material_present: np.ndarray) -> float:
    """Return the longest consecutive low-material run as a path-length fraction."""
    if material_present.size == 0:
        return 1.0

    longest_run = 0
    current_run = 0
    for present in material_present:
        if present:
            current_run = 0
        else:
            current_run += 1
            longest_run = max(longest_run, current_run)
    return longest_run / material_present.size


@mcp.tool()
def evaluate_registered_struts(
    json_filepath: str,
    mask_filepath: str,
    output_filepath: str,
    occupancy_threshold: float = 0.3,
    local_occupancy_threshold: float = 0.15,
    max_gap_fraction: float = 0.25,
    tube_radius: int = 2,
    crop_margin: float = 0.15,
    thresholds_calibrated: bool = False,
    calibration_reference: str = "",
) -> dict:
    """Evaluate registered JSON struts against a segmented CT mask.

    The matching registered JSON defines the expected graph. For each strut,
    this tool samples its 10--90% interior at two samples per voxel, evaluates
    a spherical voxel neighborhood around every centerline point using confirmed
    mask ``ZYX`` indexing, and saves frontend-compatible defect candidates plus
    auditable per-strut evidence.

    Args:
        json_filepath: Path to the registered lattice JSON blueprint.
        mask_filepath: Path to the segmented 3D ``.npy`` mask.
        output_filepath: Destination path for the results ``.json`` file.
        occupancy_threshold: Minimum unique-tube material fraction for health.
        local_occupancy_threshold: Per-centerline-sample material fraction used
            to mark material coverage and gaps.
        max_gap_fraction: Longest low-material path fraction allowed for health.
        tube_radius: Radius, in voxels, of the spherical tube neighborhood.
        crop_margin: Fraction to crop from each strut endpoint; must be < 0.5.
        thresholds_calibrated: Set True only after values were calibrated against
            an appropriate reference/control dataset.
        calibration_reference: Description or path of the calibration evidence.

    Returns:
        Structured status and the saved results path. The JSON includes
        ``defective_strut_ids`` for the existing React dashboard and detailed
        per-strut scores for scientific review.
    """
    blueprint_path = Path(json_filepath)
    mask_path = Path(mask_filepath)
    results_path = Path(output_filepath)

    if not blueprint_path.is_file():
        return {"status": "error", "message": f"Registered JSON not found: {blueprint_path}"}
    if not mask_path.is_file():
        return {"status": "error", "message": f"Segmented mask not found: {mask_path}"}
    if results_path.suffix.lower() != ".json":
        return {"status": "error", "message": "output_filepath must end with .json."}
    if not 0 <= occupancy_threshold <= 1:
        return {"status": "error", "message": "occupancy_threshold must be between 0 and 1."}
    if not 0 <= local_occupancy_threshold <= 1:
        return {"status": "error", "message": "local_occupancy_threshold must be between 0 and 1."}
    if not 0 <= max_gap_fraction <= 1:
        return {"status": "error", "message": "max_gap_fraction must be between 0 and 1."}
    if tube_radius < 0:
        return {"status": "error", "message": "tube_radius must be non-negative."}
    if not 0 <= crop_margin < 0.5:
        return {"status": "error", "message": "crop_margin must be at least 0 and less than 0.5."}
    if thresholds_calibrated and not calibration_reference.strip():
        return {
            "status": "error",
            "message": "calibration_reference is required when thresholds_calibrated is True.",
        }

    try:
        with blueprint_path.open("r", encoding="utf-8") as file:
            blueprint = json.load(file)
        if not isinstance(blueprint.get("junctions"), list) or not isinstance(blueprint.get("struts"), list):
            return {
                "status": "error",
                "message": "Registered JSON must contain junctions and struts lists.",
            }

        junctions = {
            junction["id"]: np.asarray(junction["position"], dtype=float)
            for junction in blueprint["junctions"]
        }
        mask = np.load(mask_path, mmap_mode="r")
        if mask.ndim != 3:
            return {"status": "error", "message": f"Expected a 3D mask; found shape {mask.shape}."}

        # Sphere offsets are stored in ZYX order because NumPy volumes use ZYX indexing.
        offset_axis = np.arange(-tube_radius, tube_radius + 1, dtype=int)
        offset_grid = np.stack(
            np.meshgrid(offset_axis, offset_axis, offset_axis, indexing="ij"), axis=-1
        ).reshape(-1, 3)
        tube_offsets_zyx = offset_grid[np.sum(offset_grid**2, axis=1) <= tube_radius**2]
        mask_shape = np.asarray(mask.shape)

        defective_ids = []
        strut_scores = []
        unscorable_ids = []

        for strut in blueprint["struts"]:
            strut_id = strut["id"]
            try:
                p0 = junctions[strut["junction0"]]
                p1 = junctions[strut["junction1"]]
            except KeyError:
                unscorable_ids.append(strut_id)
                strut_scores.append(
                    {"strut_id": strut_id, "classification": "unscorable", "reason": "missing junction"}
                )
                continue

            vector = p1 - p0
            length = float(np.linalg.norm(vector))
            if length == 0:
                unscorable_ids.append(strut_id)
                strut_scores.append(
                    {"strut_id": strut_id, "classification": "unscorable", "reason": "zero-length strut"}
                )
                continue

            cropped_start = p0 + vector * crop_margin
            cropped_end = p1 - vector * crop_margin
            cropped_length = length * (1 - 2 * crop_margin)
            sample_count = max(2, int(np.ceil(cropped_length * 2)) + 1)
            line_xyz = np.rint(
                np.linspace(cropped_start, cropped_end, num=sample_count)
            ).astype(int)
            line_zyx = line_xyz[:, [2, 1, 0]]

            # A local occupancy profile detects disconnected interior gaps. The
            # flattened unique coordinates prevent overlapping spheres from
            # repeatedly weighting the global tube-occupancy measurement.
            tube_zyx = line_zyx[:, np.newaxis, :] + tube_offsets_zyx[np.newaxis, :, :]
            in_bounds = np.all((tube_zyx >= 0) & (tube_zyx < mask_shape), axis=2)
            valid_counts = in_bounds.sum(axis=1)
            if not np.any(valid_counts):
                unscorable_ids.append(strut_id)
                strut_scores.append(
                    {"strut_id": strut_id, "classification": "unscorable", "reason": "outside mask bounds"}
                )
                continue

            local_values = np.zeros(in_bounds.shape, dtype=bool)
            valid_zyx = tube_zyx[in_bounds]
            local_values[in_bounds] = mask[valid_zyx[:, 0], valid_zyx[:, 1], valid_zyx[:, 2]]
            local_occupancy = local_values.sum(axis=1) / valid_counts
            material_present = local_occupancy >= local_occupancy_threshold

            unique_zyx = np.unique(valid_zyx, axis=0)
            unique_values = mask[unique_zyx[:, 0], unique_zyx[:, 1], unique_zyx[:, 2]]
            tube_occupancy = float(np.mean(unique_values))
            material_coverage = float(np.mean(material_present))
            longest_gap_fraction = _longest_low_material_gap_fraction(material_present)

            low_occupancy = tube_occupancy < occupancy_threshold
            large_gap = longest_gap_fraction > max_gap_fraction
            is_defective = low_occupancy or large_gap
            if is_defective:
                defective_ids.append(strut_id)

            strut_scores.append(
                {
                    "strut_id": strut_id,
                    "tube_occupancy": round(tube_occupancy, 6),
                    "mean_local_occupancy": round(float(np.mean(local_occupancy)), 6),
                    "material_coverage": round(material_coverage, 6),
                    "longest_low_material_gap_fraction": round(longest_gap_fraction, 6),
                    "sample_count": sample_count,
                    "unique_tube_voxels": int(len(unique_zyx)),
                    "classification": "candidate_missing_or_broken" if is_defective else "healthy",
                    "flags": {
                        "low_occupancy": low_occupancy,
                        "large_internal_gap": large_gap,
                        "thresholds_calibrated": thresholds_calibrated,
                    },
                }
            )

        total_expected = len(blueprint["struts"])
        results = {
            "status": "Analysis Complete",
            "analysis_parameters": {
                "index_order": "zyx",
                "samples_per_voxel": 2,
                "tube_radius": tube_radius,
                "crop_margin": crop_margin,
                "occupancy_threshold": occupancy_threshold,
                "local_occupancy_threshold": local_occupancy_threshold,
                "max_gap_fraction": max_gap_fraction,
                "thresholds_calibrated": thresholds_calibrated,
                "calibration_reference": calibration_reference or None,
                "calibration_warning": (
                    None
                    if thresholds_calibrated
                    else "Thresholds are provisional; calibrate against a control dataset before treating candidates as measured defects."
                ),
            },
            "summary": {
                "total_expected_struts": total_expected,
                "scorable_struts": total_expected - len(unscorable_ids),
                "unscorable_struts": len(unscorable_ids),
                "missing_defects_count": len(defective_ids),
                "defect_percentage": f"{(len(defective_ids) / total_expected * 100):.2f}%" if total_expected else "0.00%",
            },
            "defective_strut_ids": defective_ids,
            "unscorable_strut_ids": unscorable_ids,
            "strut_scores": strut_scores,
        }

        results_path.parent.mkdir(parents=True, exist_ok=True)
        with results_path.open("w", encoding="utf-8") as file:
            json.dump(results, file, indent=2)

        return {
            "status": "success",
            "message": f"Evaluated {total_expected} registered struts using ZYX mask indexing.",
            "defect_candidates": len(defective_ids),
            "unscorable_struts": len(unscorable_ids),
            "thresholds_calibrated": thresholds_calibrated,
            "results_filepath": str(results_path),
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return {"status": "error", "message": f"Error evaluating registered struts: {error}"}


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


@mcp.tool()
def analyze_strut_roi(
    strut_id: int,
    json_filepath: str,
    mask_filepath: str,
    raw_tiff_filepath: str,
    defects_filepath: str,
    output_directory: str,
    margin_voxels: int = 20,
) -> dict:
    """Create local raw-CT and mask evidence for one registered lattice strut.

    The tool reads only an endpoint-based region of interest from the memory-
    mapped TIFF and mask. It saves reproducible arrays, metadata, and orthogonal
    raw-CT views with red segmentation overlays for scientific inspection.

    Args:
        strut_id: Registered strut ID to inspect.
        json_filepath: Path to the matching registered lattice JSON graph.
        mask_filepath: Path to the matching segmented ``.npy`` mask.
        raw_tiff_filepath: Path to the matching raw 3D TIFF CT scan.
        defects_filepath: Path to the ``defects.json`` analysis results.
        output_directory: Parent directory for per-strut ROI artifacts.
        margin_voxels: Non-negative context margin around both strut endpoints.

    Returns:
        Structured ROI geometry, global evidence, calibration status, and paths
        to saved arrays, metadata, and three CT/mask overlay images.
    """
    return analyze_strut_roi_service(
        strut_id=strut_id,
        json_filepath=json_filepath,
        mask_filepath=mask_filepath,
        raw_tiff_filepath=raw_tiff_filepath,
        defects_filepath=defects_filepath,
        output_directory=output_directory,
        margin_voxels=margin_voxels,
    )

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

        roi_slices = tuple(slice(int(start), int(stop)) for start, stop in zip(roi_start_zyx, roi_stop_zyx))
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
            analysis_parameters = defects_data.get("analysis_parameters", {})
            calibration_warning = analysis_parameters.get("calibration_warning")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            global_evidence = None
            analysis_parameters = {}
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
            raw_roi[local_z, :, :],
            mask_roi[local_z, :, :],
            xy_path,
            f"Strut {strut_id}: XY at global Z={midpoint_zyx[0]}",
            "X voxel",
            "Y voxel",
            display_limits,
        )
        _save_roi_overlay(
            raw_roi[:, local_y, :],
            mask_roi[:, local_y, :],
            xz_path,
            f"Strut {strut_id}: XZ at global Y={midpoint_zyx[1]}",
            "X voxel",
            "Z voxel",
            display_limits,
        )
        _save_roi_overlay(
            raw_roi[:, :, local_x],
            mask_roi[:, :, local_x],
            yz_path,
            f"Strut {strut_id}: YZ at global X={midpoint_zyx[2]}",
            "Y voxel",
            "Z voxel",
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


@mcp.tool()
def visualize_slice(input_filepath: str, output_filepath: str, slice_index: int, axis: int = 0) -> str:
    """
    Loads a segmented 3D CT binary mask from a .npy file and saves a selected 2D slice as an image.
    
    Args:
        input_filepath: Path to the input .npy file containing the 3D segmented CT mask.
        output_filepath: Path indicating where the output image should be saved (e.g., .png).
        slice_index: The index of the slice to visualize.
        axis: The axis along which to take the slice (0, 1, or 2). Default is 0.
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    import numpy as np
    import matplotlib.pyplot as plt

    data = np.load(input_filepath)
    if data.ndim != 3:
        return f"Error: expected a 3D CT dataset, but found {data.ndim} dimensions."
    if axis not in (0, 1, 2):
        return "Error: axis must be 0, 1, or 2."
    if not 0 <= slice_index < data.shape[axis]:
        return (
            f"Error: slice_index {slice_index} is out of range for axis {axis} "
            f"(valid range: 0 to {data.shape[axis] - 1})."
        )

    slice_data = np.take(data, slice_index, axis=axis)
    plt.imsave(output_filepath, slice_data, cmap="gray", vmin=0, vmax=1)
    return f"Saved slice {slice_index} along axis {axis} to {output_filepath}"

@mcp.tool()
def skeletonize(input_filepath: str, output_filepath: str) -> str:
    """
    Creates a skeleton from a segmented 3D CT mask and saves it as a .npy file.
    
    Args:
        input_filepath: Path to the .npy file containing the 3D mask.
        output_filepath: Path to save the extracted skeleton (.npy).
        
    Returns:
        A status message indicating success and the save location, or an error message.
    """
    from pathlib import Path
    import sys

    if not Path(input_filepath).exists():
        return f"Error: input file not found at {input_filepath}"

    source_directory = str(Path(__file__).resolve().parent)
    if source_directory not in sys.path:
        sys.path.insert(0, source_directory)

    from skeletonization import skeletonize_mask

    skeletonize_mask(file_path=input_filepath, output_path=output_filepath)
    return f"Saved skeleton to {output_filepath}"

if __name__ == "__main__":
    # Run the FastMCP server, exposing the tools over standard I/O (default)
    mcp.run()
