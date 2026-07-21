# Unitcell Metadata and Threshold Optimization Report

## Scope

This report records the metadata extraction performed on every NumPy (`.npy`) file under `data/`, followed by threshold-based segmentation of the raw unitcell CT scan at distribution-derived percentile thresholds.

## Metadata extraction results

| File | Shape | Data type | Minimum | Maximum | Mean |
|---|---:|---|---:|---:|---:|
| `data/unitcell/unitcell_segmented.npy` | `(256, 256, 256)` | `uint8` | 0 | 1 | 0.04302108287811279 |
| `data/unitcell/unitcell_skeleton.npy` | `(256, 256, 256)` | `bool` | `False` | `True` | 0.00018912553787231445 |
| `data/unitcell/unitcell.npy` | `(256, 256, 256)` | `float32` | -0.003128750016912818 | 0.015257691964507103 | 0.0005390668520703912 |

## Raw scan and candidate thresholds

The raw 3D scan used for optimization was `data/unitcell/unitcell.npy`.

Its observed value range was -0.003128750016912818 to 0.015257691964507103. Candidate thresholds were calculated directly from the scan's voxel-value distribution:

| Percentile | Threshold |
|---|---:|
| 75th (`p75`) | 0.00017947150627151132 |
| 90th (`p90`) | 0.00056093043531291187 |
| 95th (`p95`) | 0.0021166288643144071 |

## Segmentation results

Each output is a binary mask where source voxels greater than or equal to the listed threshold are foreground.

| Percentile | Threshold | Output file | Foreground voxels | Total voxels | Foreground percentage | Status |
|---|---:|---|---:|---:|---:|---|
| 75th | 0.00017947150627151132 | `data/unitcell/unitcell_seg_p75.npy` | 4,194,304 | 16,777,216 | 25.000000% | Usable; not degenerate |
| 90th | 0.00056093043531291187 | `data/unitcell/unitcell_seg_p90.npy` | 1,677,722 | 16,777,216 | 10.000002% | Usable; not degenerate |
| 95th | 0.0021166288643144071 | `data/unitcell/unitcell_seg_p95.npy` | 838,861 | 16,777,216 | 5.000001% | Usable; not degenerate |

No output was empty or entirely foreground.

## Generated outputs

- `data/unitcell/unitcell_seg_p75.npy`
- `data/unitcell/unitcell_seg_p90.npy`
- `data/unitcell/unitcell_seg_p95.npy`
