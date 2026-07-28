import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.evidence_provenance import (
    BASE_EVIDENCE_PROVENANCE_KEY,
    BASE_EVIDENCE_PROVENANCE_VERSION,
    base_evidence_errors,
    file_fingerprint,
)
from src.mask_morphology import (
    BORDER_VALUE,
    ITERATIONS,
    MORPHOLOGY_LIBRARY,
    MORPHOLOGY_OPERATION,
    MORPHOLOGY_VERSION,
    STRUCTURE_SHAPE,
)


class EvidenceProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.graph_path = self.root / "registered.json"
        self.live_mask_path = self.root / "mask.npy"
        self.raw_mask_path = self.root / "mask.raw.npy"
        self.graph_path.write_text(
            json.dumps({"junctions": [], "struts": [{"id": 1}]}),
            encoding="utf-8",
        )
        raw_mask = np.zeros((5, 5, 5), dtype=bool)
        raw_mask[1:4, 1:4, 1:4] = True
        np.save(self.raw_mask_path, raw_mask)
        np.save(self.live_mask_path, raw_mask)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _results(self, include_preprocessing: bool = True) -> dict:
        live_mask = file_fingerprint(self.live_mask_path, self.root, include_sha256=True)
        provenance = {
            "schema_version": BASE_EVIDENCE_PROVENANCE_VERSION,
            "coordinate_source": "registered_json",
            "registered_graph": {
                **file_fingerprint(self.graph_path, self.root, include_sha256=True),
                "strut_count": 1,
            },
            "segmentation_mask": live_mask,
        }
        if include_preprocessing:
            provenance["mask_preprocessing"] = {
                "version": MORPHOLOGY_VERSION,
                "operation": MORPHOLOGY_OPERATION,
                "library": MORPHOLOGY_LIBRARY,
                "structure_shape": list(STRUCTURE_SHAPE),
                "iterations": ITERATIONS,
                "border_value": BORDER_VALUE,
                "source_mask": file_fingerprint(self.raw_mask_path, self.root, include_sha256=True),
                "output_mask": live_mask,
                "foreground_voxels_before": 27,
                "foreground_voxels_after": 27,
                "voxels_added": 0,
                "voxels_removed": 0,
                "voxels_changed": 0,
            }
        return {
            "analysis_parameters": {BASE_EVIDENCE_PROVENANCE_KEY: provenance},
            "strut_scores": [{"strut_id": 1}],
        }

    def test_valid_closing_provenance_is_accepted(self) -> None:
        self.assertEqual(
            base_evidence_errors(
                self._results(),
                root=self.root,
                registered_graph_path=self.graph_path,
                mask_path=self.live_mask_path,
                raw_mask_path=self.raw_mask_path,
            ),
            [],
        )

    def test_legacy_evidence_without_closing_is_rejected(self) -> None:
        errors = base_evidence_errors(
            self._results(include_preprocessing=False),
            root=self.root,
            registered_graph_path=self.graph_path,
            mask_path=self.live_mask_path,
            raw_mask_path=self.raw_mask_path,
        )
        self.assertIn("required morphological-closing provenance is missing", errors)

    def test_changed_raw_source_is_rejected(self) -> None:
        results = self._results()
        changed_mask = np.ones((5, 5, 5), dtype=bool)
        np.save(self.raw_mask_path, changed_mask)
        os.utime(self.raw_mask_path, None)

        errors = base_evidence_errors(
            results,
            root=self.root,
            registered_graph_path=self.graph_path,
            mask_path=self.live_mask_path,
            raw_mask_path=self.raw_mask_path,
        )
        self.assertIn("raw segmentation mask changed after base evidence was generated", errors)


if __name__ == "__main__":
    unittest.main()
