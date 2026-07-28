"""Unit tests for the autonomous CAD-to-CT registration primitives.

These tests deliberately use synthetic point clouds: they verify the maths and
the output contract without depending on the large challenge TIFF.
"""

from __future__ import annotations

import unittest

import numpy as np

from src.autonomous_registration import (
    infer_nearby_lattice_symmetry_offsets,
    resolve_lattice_translation_symmetry,
    RegistrationConfig,
    SimilarityTransform,
    _rotation_matrix,
    build_registered_graph,
    solve_similarity_transform,
    synthetic_recovery_check,
)


class AutonomousRegistrationTests(unittest.TestCase):
    def test_similarity_solver_recovers_known_transform(self) -> None:
        rng = np.random.default_rng(81)
        source = rng.normal(size=(80, 3))
        expected = SimilarityTransform(
            scale=17.25,
            rotation=_rotation_matrix(2, 7.0) @ _rotation_matrix(0, -3.0),
            translation=np.array([40.0, -11.0, 92.0]),
        )
        recovered = solve_similarity_transform(source, expected.apply(source))
        np.testing.assert_allclose(recovered.apply(source), expected.apply(source), atol=1e-9)
        self.assertAlmostEqual(recovered.scale, expected.scale, places=9)

    def test_seeded_trimmed_icp_synthetic_recovery_passes(self) -> None:
        result = synthetic_recovery_check()
        self.assertTrue(result["passed"])
        self.assertLessEqual(result["p95_recovery_error_voxels"], 0.5)

    def test_registered_graph_preserves_strut_connectivity_and_ids(self) -> None:
        graph = {
            "junctions": [
                {"id": 10, "position": [0.0, 0.0, 0.0]},
                {"id": 20, "position": [1.0, 0.0, 0.0]},
            ],
            "struts": [{"id": 33, "start_junction_id": 10, "end_junction_id": 20}],
            "unit_cells": [{"id": 1, "strut_ids": [33]}],
        }
        coarse = np.array([[3.0, 4.0, 5.0], [6.0, 7.0, 8.0]])
        refined = coarse + 0.25
        records = [
            {"status": "refined", "shift_voxels": 0.43, "peak_radius_voxels": 2.1},
            {"status": "coarse_retained", "shift_voxels": None, "peak_radius_voxels": None},
        ]
        output = build_registered_graph(graph, coarse, refined, records, {"status": "validated"})
        self.assertEqual(output["struts"], graph["struts"])
        self.assertEqual(output["unit_cells"], graph["unit_cells"])
        self.assertEqual(output["junctions"][0]["id"], 10)
        self.assertEqual(output["junctions"][0]["cad_position"], [0.0, 0.0, 0.0])
        self.assertEqual(output["junctions"][0]["position"], [3.25, 4.25, 5.25])

    def test_octet_parity_detects_valid_local_translation_symmetry(self) -> None:
        # The four even-parity basis points reproduce the octet graph's local
        # integer-grid parity rule. (0, 1, 1) preserves that rule; (1, 0, 0)
        # does not.
        points = np.array([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=float)
        offsets = infer_nearby_lattice_symmetry_offsets(points)
        self.assertIn((0, 1, 1), offsets)
        self.assertNotIn((1, 0, 0), offsets)

    def test_symmetry_resolution_selects_ct_supported_in_bounds_offset(self) -> None:
        cad = np.array([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=float)
        baseline = SimilarityTransform(1.0, np.eye(3), np.array([0.2, -1.0, -1.0]))
        expected = baseline.apply(cad) + np.array([0.0, 1.0, 1.0])
        selected, audit = resolve_lattice_translation_symmetry(
            baseline,
            cad,
            expected,
            expected,
            (5, 5, 5),
            RegistrationConfig(),
        )
        self.assertEqual(audit["selected_offset_cad_xyz"], [0, 1, 1])
        np.testing.assert_allclose(selected.apply(cad), expected)
        self.assertTrue(audit["selected_metrics"]["eligible"])


if __name__ == "__main__":
    unittest.main()
