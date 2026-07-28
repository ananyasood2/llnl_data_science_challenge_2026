"""Helpers for proving CT evidence was generated from the registered graph."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.mask_morphology import (
    BORDER_VALUE,
    ITERATIONS,
    MORPHOLOGY_LIBRARY,
    MORPHOLOGY_OPERATION,
    MORPHOLOGY_VERSION,
    STRUCTURE_SHAPE,
)

BASE_EVIDENCE_PROVENANCE_KEY = "base_evidence_provenance"
BASE_EVIDENCE_PROVENANCE_VERSION = 2


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a deterministic SHA-256 for a file without materializing it."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def relative_path(path: Path, root: Path) -> str:
    """Return a portable, repository-relative path when possible."""

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def file_fingerprint(path: Path, root: Path, *, include_sha256: bool) -> dict[str, Any]:
    """Capture the source identity needed to detect stale evidence."""

    stat = path.stat()
    fingerprint: dict[str, Any] = {
        "path": relative_path(path, root),
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }
    if include_sha256:
        fingerprint["sha256"] = file_sha256(path)
    return fingerprint


def registered_strut_ids(graph_path: Path) -> frozenset[int]:
    """Read and validate the stable IDs in a registered lattice graph."""

    with graph_path.open("r", encoding="utf-8") as source:
        graph = json.load(source)
    struts = graph.get("struts")
    if not isinstance(struts, list) or not struts:
        raise ValueError("Registered graph must contain a non-empty struts list.")
    try:
        ids = [int(strut["id"]) for strut in struts]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Registered graph has invalid strut IDs: {error}") from error
    if len(set(ids)) != len(ids):
        raise ValueError("Registered graph contains duplicate strut IDs.")
    return frozenset(ids)


def score_id_errors(results: dict[str, Any], expected_ids: frozenset[int]) -> list[str]:
    """Return validation errors when result scores do not match the graph IDs."""

    scores = results.get("strut_scores")
    if not isinstance(scores, list):
        return ["strut_scores must be an array"]
    try:
        score_ids = [int(score["strut_id"]) for score in scores]
    except (KeyError, TypeError, ValueError) as error:
        return [f"strut_scores has an invalid strut_id: {error}"]
    if len(score_ids) != len(expected_ids):
        return [
            f"strut_scores count {len(score_ids)} does not match registered graph count {len(expected_ids)}"
        ]
    if len(set(score_ids)) != len(score_ids):
        return ["strut_scores contains duplicate strut IDs"]
    if frozenset(score_ids) != expected_ids:
        return ["strut_scores IDs do not exactly match the registered graph"]
    return []


def base_evidence_errors(
    results: dict[str, Any],
    *,
    root: Path,
    registered_graph_path: Path,
    mask_path: Path,
    raw_mask_path: Path | None = None,
) -> list[str]:
    """Return stale/provenance errors without hashing the large mask per request."""

    parameters = results.get("analysis_parameters")
    if not isinstance(parameters, dict):
        return ["analysis_parameters is missing"]
    provenance = parameters.get(BASE_EVIDENCE_PROVENANCE_KEY)
    if not isinstance(provenance, dict):
        return ["registered-graph base evidence provenance is missing"]
    if provenance.get("schema_version") != BASE_EVIDENCE_PROVENANCE_VERSION:
        return ["registered-graph base evidence provenance version is unsupported"]
    if provenance.get("coordinate_source") != "registered_json":
        return ["base evidence was not generated from the registered JSON graph"]

    registered_graph = provenance.get("registered_graph")
    if not isinstance(registered_graph, dict):
        return ["registered graph provenance is missing"]
    expected_graph_path = relative_path(registered_graph_path, root)
    if registered_graph.get("path") != expected_graph_path:
        return ["base evidence references a different graph path"]
    if registered_graph.get("sha256") != file_sha256(registered_graph_path):
        return ["registered graph changed after base evidence was generated"]

    expected_ids = registered_strut_ids(registered_graph_path)
    if registered_graph.get("strut_count") != len(expected_ids):
        return ["registered graph strut-count provenance does not match the current graph"]

    mask = provenance.get("segmentation_mask")
    if not isinstance(mask, dict):
        return ["segmentation mask provenance is missing"]
    expected_mask_path = relative_path(mask_path, root)
    mask_stat = mask_path.stat()
    if mask.get("path") != expected_mask_path:
        return ["base evidence references a different segmentation mask"]
    if mask.get("size_bytes") != mask_stat.st_size or mask.get("modified_ns") != mask_stat.st_mtime_ns:
        return ["segmentation mask changed after base evidence was generated"]
    if not isinstance(mask.get("sha256"), str):
        return ["segmentation mask provenance hash is missing"]

    preprocessing = provenance.get("mask_preprocessing")
    if not isinstance(preprocessing, dict):
        return ["required morphological-closing provenance is missing"]
    if preprocessing.get("version") != MORPHOLOGY_VERSION:
        return ["morphological-closing provenance version is unsupported"]
    if preprocessing.get("operation") != MORPHOLOGY_OPERATION:
        return ["base evidence was not generated with binary closing"]
    if preprocessing.get("library") != MORPHOLOGY_LIBRARY:
        return ["base evidence uses an unexpected morphology implementation"]
    if preprocessing.get("structure_shape") != list(STRUCTURE_SHAPE):
        return ["base evidence does not use the required 3x3x3 closing kernel"]
    if preprocessing.get("iterations") != ITERATIONS or preprocessing.get("border_value") != BORDER_VALUE:
        return ["base evidence uses unexpected closing parameters"]

    output_mask = preprocessing.get("output_mask")
    if output_mask != mask:
        return ["morphological-closing output provenance does not match the live mask"]

    if raw_mask_path is None:
        return ["raw segmentation-mask path is required for morphology provenance validation"]
    source_mask = preprocessing.get("source_mask")
    if not isinstance(source_mask, dict):
        return ["morphological-closing source-mask provenance is missing"]
    raw_stat = raw_mask_path.stat()
    if source_mask.get("path") != relative_path(raw_mask_path, root):
        return ["morphological-closing provenance references a different raw mask"]
    if (
        source_mask.get("size_bytes") != raw_stat.st_size
        or source_mask.get("modified_ns") != raw_stat.st_mtime_ns
    ):
        return ["raw segmentation mask changed after base evidence was generated"]
    if not isinstance(source_mask.get("sha256"), str):
        return ["raw segmentation-mask provenance hash is missing"]

    return score_id_errors(results, expected_ids)
