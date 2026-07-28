import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.mask_morphology import close_binary_mask
from regenerate_registered_defects import _masks_are_equal


class MaskMorphologyTests(unittest.TestCase):
    def test_closing_fills_a_single_voxel_hole(self) -> None:
        mask = np.zeros((9, 9, 9), dtype=bool)
        mask[2:7, 2:7, 2:7] = True
        mask[4, 4, 4] = False

        closed = close_binary_mask(mask)

        self.assertTrue(closed[4, 4, 4])

    def test_closing_preserves_shape_dtype_and_is_idempotent(self) -> None:
        mask = np.zeros((9, 9, 9), dtype=bool)
        mask[2:7, 2:7, 2:7] = True
        mask[4, 4, 4] = False

        closed_once = close_binary_mask(mask)
        closed_twice = close_binary_mask(closed_once)

        self.assertEqual(closed_once.shape, mask.shape)
        self.assertEqual(closed_once.dtype, np.dtype(bool))
        np.testing.assert_array_equal(closed_twice, closed_once)

    def test_closing_does_not_fill_the_center_of_a_wide_gap(self) -> None:
        mask = np.zeros((11, 11, 11), dtype=bool)
        mask[2:9, 2:9, 2:4] = True
        mask[2:9, 2:9, 7:9] = True

        closed = close_binary_mask(mask)

        self.assertFalse(closed[5, 5, 5])

    def test_closing_preserves_material_at_the_volume_edge(self) -> None:
        mask = np.zeros((9, 9, 9), dtype=bool)
        mask[0:5, 2:7, 2:7] = True

        closed = close_binary_mask(mask)

        self.assertTrue(closed[0, 4, 4])

    def test_identical_mask_detection_compares_content_not_paths(self) -> None:
        mask = np.zeros((5, 5, 5), dtype=bool)
        mask[2, 2, 2] = True
        with TemporaryDirectory() as directory:
            left = Path(directory) / "left.npy"
            right = Path(directory) / "right.npy"
            np.save(left, mask)
            np.save(right, mask)
            self.assertTrue(_masks_are_equal(left, right))
            mask[0, 0, 0] = True
            np.save(right, mask)
            self.assertFalse(_masks_are_equal(left, right))


if __name__ == "__main__":
    unittest.main()
