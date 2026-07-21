# Metadata Extraction Report

## Scope

This report captures the results from the `metadata-extractor` workflow run on all NumPy (`.npy`) files present under `data/` at the time of extraction. The workflow loads each array and reports its shape, data type, minimum, maximum, and mean.

## Results

| File | Shape | Data type | Minimum | Maximum | Mean |
|---|---:|---|---:|---:|---:|
| `data/unitcell/unitcell_segmented.npy` | `(256, 256, 256)` | `uint8` | 0 | 1 | 0.04302108287811279 |
| `data/unitcell/unitcell_skeleton.npy` | `(256, 256, 256)` | `bool` | `False` | `True` | 0.00018912553787231445 |
| `data/unitcell/unitcell.npy` | `(256, 256, 256)` | `float32` | -0.003128750016912818 | 0.015257691964507103 | 0.0005390668520703912 |

## Notes

- All three arrays loaded successfully.
- Each array has shape `(256, 256, 256)`.
- `unitcell.npy` is the raw floating-point CT scan.
- `unitcell_segmented.npy` is a binary `uint8` mask, while `unitcell_skeleton.npy` is a boolean mask.
