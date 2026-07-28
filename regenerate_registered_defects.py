"""Regenerate base strut evidence from the validated registered lattice graph.

This is a deliberate, one-time analysis operation.  Slider changes must use
the resulting evidence and never rerun CT occupancy analysis.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.evidence_provenance import (
    BASE_EVIDENCE_PROVENANCE_KEY,
    BASE_EVIDENCE_PROVENANCE_VERSION,
    base_evidence_errors,
    file_fingerprint,
    registered_strut_ids,
    score_id_errors,
)
from src.mask_morphology import (
    BORDER_VALUE,
    ITERATIONS,
    MORPHOLOGY_LIBRARY,
    MORPHOLOGY_OPERATION,
    MORPHOLOGY_VERSION,
    STRUCTURE_SHAPE,
    close_binary_mask,
)
from src.mcp_server import evaluate_registered_struts, validate_registered_alignment


ROOT = Path(__file__).resolve().parent
REGISTERED_GRAPH_PATH = (
    ROOT
    / "data"
    / "missing_struts"
    / "registered_jsons"
    / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"
)
MASK_PATH = ROOT / "data" / "missing_struts" / "segmentation" / "0point5dash1_mask.npy"
RAW_MASK_PATH = MASK_PATH.with_name("0point5dash1_mask.raw.npy")
DEFECTS_PATH = ROOT / "data" / "missing_struts" / "segmentation" / "defects.json"

MIN_ALIGNMENT_HIT_RATE = 0.80
ALIGNMENT_SAMPLE_COUNT = 512
ALIGNMENT_NEIGHBORHOOD_RADIUS = 2
EVIDENCE_PARAMETERS = {
    "occupancy_threshold": 0.3,
    "local_occupancy_threshold": 0.15,
    "max_gap_fraction": 0.25,
    "tube_radius": 2,
    "crop_margin": 0.15,
    "thresholds_calibrated": False,
    "calibration_reference": "",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _temporary_path(prefix: str, suffix: str) -> Path:
    """Reserve a same-directory temporary path suitable for atomic replacement."""

    descriptor, temporary_path = tempfile.mkstemp(
        prefix=prefix,
        suffix=suffix,
        dir=MASK_PATH.parent,
    )
    os.close(descriptor)
    return Path(temporary_path)


def _validate_binary_mask(path: Path, label: str, expected_shape: tuple[int, ...] | None = None) -> tuple[int, ...]:
    """Ensure a mask artifact is a 3D boolean volume with the expected shape."""

    mask = np.load(path, mmap_mode="r")
    try:
        if mask.ndim != 3:
            raise ValueError(f"{label} must be 3D; found shape {mask.shape}.")
        if mask.dtype != np.dtype(bool):
            raise ValueError(f"{label} must use boolean dtype; found {mask.dtype}.")
        shape = tuple(int(value) for value in mask.shape)
        if expected_shape is not None and shape != expected_shape:
            raise ValueError(f"{label} shape {shape} does not match expected shape {expected_shape}.")
        return shape
    finally:
        del mask


def _ensure_raw_mask_backup() -> bool:
    """Retain the pre-closing segmentation once, without replacing an existing backup."""

    if RAW_MASK_PATH.exists():
        _validate_binary_mask(RAW_MASK_PATH, "Raw segmentation-mask backup")
        return False

    backup_stage = _temporary_path("mask.raw.", ".npy")
    try:
        shutil.copy2(MASK_PATH, backup_stage)
        _validate_binary_mask(backup_stage, "Staged raw segmentation-mask backup")
        os.replace(backup_stage, RAW_MASK_PATH)
        return True
    finally:
        backup_stage.unlink(missing_ok=True)


def _mask_change_counts(source_mask: np.ndarray, closed_mask: np.ndarray) -> tuple[int, int]:
    """Count morphology additions/removals in slabs to limit temporary memory."""

    added = 0
    removed = 0
    for start in range(0, source_mask.shape[0], 32):
        stop = min(start + 32, source_mask.shape[0])
        source_block = np.asarray(source_mask[start:stop], dtype=bool)
        closed_block = closed_mask[start:stop]
        added += int(np.count_nonzero(np.logical_and(~source_block, closed_block)))
        removed += int(np.count_nonzero(np.logical_and(source_block, ~closed_block)))
    return added, removed


def _stage_closed_mask() -> tuple[Path, dict]:
    """Close the preserved raw mask and write a verified temporary mask artifact."""

    source_mask = np.load(RAW_MASK_PATH, mmap_mode="r")
    try:
        source_shape = _validate_binary_mask(RAW_MASK_PATH, "Raw segmentation-mask backup")
        foreground_before = int(np.count_nonzero(source_mask))
        closed_mask = close_binary_mask(source_mask)
        if tuple(closed_mask.shape) != source_shape or closed_mask.dtype != np.dtype(bool):
            raise RuntimeError("Morphological closing did not preserve the expected boolean mask shape.")
        foreground_after = int(np.count_nonzero(closed_mask))
        voxels_added, voxels_removed = _mask_change_counts(source_mask, closed_mask)
    finally:
        del source_mask

    staged_mask = _temporary_path("mask.closed.", ".npy")
    try:
        np.save(staged_mask, closed_mask)
        del closed_mask
        _validate_binary_mask(staged_mask, "Staged closed segmentation mask", source_shape)
        return staged_mask, {
            "foreground_voxels_before": foreground_before,
            "foreground_voxels_after": foreground_after,
            "voxels_added": voxels_added,
            "voxels_removed": voxels_removed,
            "voxels_changed": voxels_added + voxels_removed,
        }
    except Exception:
        staged_mask.unlink(missing_ok=True)
        raise


def _alignment_or_raise(mask_path: Path) -> dict:
    alignment = validate_registered_alignment(
        json_filepath=str(REGISTERED_GRAPH_PATH),
        mask_filepath=str(mask_path),
        sample_count=ALIGNMENT_SAMPLE_COUNT,
        neighborhood_radius=ALIGNMENT_NEIGHBORHOOD_RADIUS,
    )
    zyx_hit_rate = alignment.get("candidate_results", {}).get("zyx", {}).get("hit_rate", 0.0)
    if (
        alignment.get("status") != "success"
        or alignment.get("recommended_index_order") != "zyx"
        or not alignment.get("is_valid")
        or zyx_hit_rate < MIN_ALIGNMENT_HIT_RATE
    ):
        raise RuntimeError(
            "Registered graph alignment did not meet the required ZYX hit rate "
            f"of {MIN_ALIGNMENT_HIT_RATE:.2f}: {alignment}"
        )
    return alignment


def _provenance(alignment: dict, graph_ids: frozenset[int], mask_change_summary: dict) -> dict:
    raw_mask = file_fingerprint(RAW_MASK_PATH, ROOT, include_sha256=True)
    closed_mask = file_fingerprint(MASK_PATH, ROOT, include_sha256=True)
    return {
        "schema_version": BASE_EVIDENCE_PROVENANCE_VERSION,
        "coordinate_source": "registered_json",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "registered_graph": {
            **file_fingerprint(REGISTERED_GRAPH_PATH, ROOT, include_sha256=True),
            "strut_count": len(graph_ids),
        },
        "segmentation_mask": closed_mask,
        "mask_preprocessing": {
            "version": MORPHOLOGY_VERSION,
            "operation": MORPHOLOGY_OPERATION,
            "library": MORPHOLOGY_LIBRARY,
            "structure_shape": list(STRUCTURE_SHAPE),
            "iterations": ITERATIONS,
            "border_value": BORDER_VALUE,
            "source_mask": raw_mask,
            "output_mask": closed_mask,
            **mask_change_summary,
        },
        "alignment_validation": {
            "minimum_zyx_hit_rate": MIN_ALIGNMENT_HIT_RATE,
            "sampled_junctions": ALIGNMENT_SAMPLE_COUNT,
            "neighborhood_radius": ALIGNMENT_NEIGHBORHOOD_RADIUS,
            "recommended_index_order": alignment["recommended_index_order"],
            "is_valid": alignment["is_valid"],
            "candidate_results": alignment["candidate_results"],
        },
        "evidence_parameters": EVIDENCE_PARAMETERS,
    }


def regenerate_registered_defects() -> dict:
    """Build, validate, back up, and atomically publish registered-graph evidence."""

    for label, path in (
        ("Registered graph", REGISTERED_GRAPH_PATH),
        ("Live segmentation mask", MASK_PATH),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")

    raw_mask_backup_created = _ensure_raw_mask_backup()
    graph_ids = registered_strut_ids(REGISTERED_GRAPH_PATH)
    staged_mask, mask_change_summary = _stage_closed_mask()
    temporary_path = _temporary_path("defects.registered.", ".json")
    rollback_mask = _temporary_path("mask.rollback.", ".npy")
    mask_replaced = False
    defects_published = False

    try:
        alignment = _alignment_or_raise(staged_mask)
        evaluation = evaluate_registered_struts(
            json_filepath=str(REGISTERED_GRAPH_PATH),
            mask_filepath=str(staged_mask),
            output_filepath=str(temporary_path),
            **EVIDENCE_PARAMETERS,
        )
        if evaluation.get("status") != "success":
            raise RuntimeError(f"Registered evidence evaluation failed: {evaluation}")

        with temporary_path.open("r", encoding="utf-8") as source:
            results = json.load(source)
        score_errors = score_id_errors(results, graph_ids)
        if score_errors:
            raise RuntimeError("Generated evidence has invalid score IDs: " + "; ".join(score_errors))

        # Retain a byte-for-byte rollback artifact until both live files publish.
        shutil.copy2(MASK_PATH, rollback_mask)
        os.replace(staged_mask, MASK_PATH)
        mask_replaced = True

        analysis_parameters = results.setdefault("analysis_parameters", {})
        analysis_parameters[BASE_EVIDENCE_PROVENANCE_KEY] = _provenance(
            alignment,
            graph_ids,
            mask_change_summary,
        )

        errors = base_evidence_errors(
            results,
            root=ROOT,
            registered_graph_path=REGISTERED_GRAPH_PATH,
            mask_path=MASK_PATH,
            raw_mask_path=RAW_MASK_PATH,
        )
        if errors:
            raise RuntimeError("Generated evidence failed validation: " + "; ".join(errors))

        with temporary_path.open("w", encoding="utf-8") as output:
            json.dump(results, output, indent=2)
            output.write("\n")

        backup_path = None
        if DEFECTS_PATH.exists():
            backup_path = DEFECTS_PATH.with_name(
                f"defects.pre_registered_refresh.{_timestamp()}.json"
            )
            shutil.copy2(DEFECTS_PATH, backup_path)
        os.replace(temporary_path, DEFECTS_PATH)
        defects_published = True
        return {
            "status": "success",
            "results_path": str(DEFECTS_PATH),
            "backup_path": str(backup_path) if backup_path else None,
            "registered_strut_count": len(graph_ids),
            "zyx_hit_rate": alignment["candidate_results"]["zyx"]["hit_rate"],
            "legacy_candidate_count": results["summary"]["missing_defects_count"],
            "raw_mask_backup_path": str(RAW_MASK_PATH),
            "raw_mask_backup_created": raw_mask_backup_created,
            "mask_preprocessing": mask_change_summary,
        }
    except Exception:
        if mask_replaced and not defects_published:
            os.replace(rollback_mask, MASK_PATH)
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        staged_mask.unlink(missing_ok=True)
        rollback_mask.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(regenerate_registered_defects(), indent=2))
