from __future__ import annotations

import numpy as np
from scipy import ndimage

from lattice_pipeline.align import bbox_match_alignment, refine_positions_to_skeleton
from lattice_pipeline.defects import DefectConfig, classify_defects
from lattice_pipeline.segment import segment_with_metadata
from lattice_pipeline.skeleton import analyze_skeleton, label_skeleton_components
from lattice_pipeline.validation import (
    evaluate_against_intentional_missing,
    mark_unreliable_boundary_faces,
)


def test_otsu_uses_native_intensity_range() -> None:
    volume = np.zeros((8, 8, 8), dtype=np.float32)
    volume[2:6, 2:6, 2:6] = 0.012
    mask, metadata = segment_with_metadata(volume)
    assert mask.sum() == 64
    assert 0 <= metadata["threshold"] < 0.012


def test_diagonal_skeleton_is_one_component_with_26_connectivity() -> None:
    skeleton = np.zeros((5, 5, 5), dtype=bool)
    skeleton[1, 1, 1] = True
    skeleton[2, 2, 2] = True
    skeleton[3, 3, 3] = True
    _, count = label_skeleton_components(skeleton)
    assert count == 1
    assert analyze_skeleton(skeleton, include_graph=False)["connectivity"] == 26


def test_bbox_alignment_maps_design_extents_to_scan_extents() -> None:
    design = np.asarray([[0, 0, 0], [2, 2, 2]], dtype=float)
    transform = bbox_match_alignment(
        design, {"min_xyz": [37, 37, 37], "max_xyz": [218, 218, 218]}
    )
    np.testing.assert_allclose(transform.scale, [90.5, 90.5, 90.5])
    np.testing.assert_allclose(transform.apply(design), [[37, 37, 37], [218, 218, 218]])


def test_absent_design_strut_is_missing_and_schema_is_complete() -> None:
    mask = np.zeros((24, 24, 24), dtype=bool)
    skeleton = np.zeros_like(mask)
    distance = ndimage.distance_transform_edt(mask)
    nodes = [
        {"id": 0, "position": [2, 12, 12]},
        {"id": 1, "position": [21, 12, 12]},
    ]
    struts = [{"id": 7, "junction0": 0, "junction1": 1}]
    result = classify_defects(
        mask,
        skeleton,
        distance,
        nodes,
        struts,
        0.05,
        config=DefectConfig(nominal_thickness_um=350),
    )
    assert result["struts"][0]["status"] == "missing"
    assert result["defects"][0]["affected_element"] == {"kind": "strut", "id": 7}
    assert 0 <= result["defects"][0]["confidence"] <= 1
    assert result["summary"]["connectivity"] == 26


def test_robust_refinement_moves_registered_edges_toward_skeleton() -> None:
    positions = np.asarray(
        [[4, 4, 4], [14, 4, 4], [4, 14, 4], [4, 4, 14]],
        dtype=float,
    )
    edges = np.asarray(
        [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]],
        dtype=int,
    )
    target = positions * 0.94 + np.asarray([1.5, 1.0, 1.25])
    skeleton = np.zeros((20, 20, 20), dtype=bool)
    for start, end in edges:
        points = np.linspace(target[start], target[end], 80)
        xyz = np.rint(points).astype(int)
        skeleton[xyz[:, 2], xyz[:, 1], xyz[:, 0]] = True

    refined, metadata = refine_positions_to_skeleton(
        positions,
        edges,
        skeleton,
        iterations=8,
    )
    skeleton_xyz = np.argwhere(skeleton)[:, ::-1]
    before = np.min(
        np.linalg.norm(positions[:, None] - skeleton_xyz[None, :], axis=2),
        axis=1,
    )
    after = np.min(
        np.linalg.norm(refined[:, None] - skeleton_xyz[None, :], axis=2),
        axis=1,
    )

    assert metadata["applied"]
    assert np.median(after) < np.median(before)


def test_scan_wide_missing_face_is_downgraded_to_uncertain() -> None:
    nominal = {
        "junctions": [
            {"id": 0, "position": [0, 0, 0]},
            {"id": 1, "position": [1, 0, 0]},
            {"id": 2, "position": [0, 1, 0]},
            {"id": 3, "position": [1, 1, 0]},
        ],
        "struts": [
            {"id": 0, "junction0": 0, "junction1": 1},
            {"id": 1, "junction0": 2, "junction1": 3},
        ],
    }
    result = {
        "struts": [
            {"id": 0, "status": "healthy", "present_fraction": 1.0},
            {"id": 1, "status": "missing", "present_fraction": 0.0},
        ],
        "nodes": [
            {"id": 0, "status": "healthy"},
            {"id": 1, "status": "healthy"},
            {"id": 2, "status": "missing"},
            {"id": 3, "status": "missing"},
        ],
        "defects": [
            {
                "type": "missing",
                "severity": "high",
                "confidence": 0.98,
                "affected_element": {"kind": "strut", "id": 1},
            }
        ],
    }

    faces = mark_unreliable_boundary_faces(
        result,
        nominal,
        missing_present_fraction=0.15,
        unreliable_missing_rate=0.75,
    )

    assert {f"{face['axis']}-{face['side']}" for face in faces} == {"Y-high"}
    assert result["struts"][1]["status"] == "uncertain"
    assert result["nodes"][2]["status"] == "uncertain"
    assert result["defects"][0]["type"] == "uncertain"


def test_id_level_validation_reports_false_positives_and_negatives() -> None:
    nominal = {
        "junctions": [
            {"id": 0, "position": [0, 0, 0]},
            {"id": 1, "position": [1, 0, 0]},
            {"id": 2, "position": [2, 0, 0]},
        ],
        "struts": [
            {"id": 10, "junction0": 0, "junction1": 1},
            {"id": 11, "junction0": 1, "junction1": 2},
        ],
    }
    result = {
        "struts": [
            {"id": 10, "status": "missing"},
            {"id": 11, "status": "healthy"},
            {"id": 12, "status": "missing"},
        ],
        "nodes": [
            {"id": 0, "status": "missing"},
            {"id": 1, "status": "healthy"},
            {"id": 2, "status": "healthy"},
        ],
    }

    validation = evaluate_against_intentional_missing(
        result,
        nominal,
        [10, 11],
    )

    assert validation["struts"]["true_positive"] == 1
    assert validation["struts"]["false_positive"] == 1
    assert validation["struts"]["false_negative"] == 1
