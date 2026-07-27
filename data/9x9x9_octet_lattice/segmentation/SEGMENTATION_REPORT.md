# Segmentation Report

- date: 2026-07-21
- input volume: `/private/tmp/9x9x9_octet_lattice.tif`
- ground truth image: `data/9x9x9_octet_lattice/ground_truth_segmentation_slice_380.png`
- volume shape: `(761, 815, 837)`
- volume dtype: `>u2`
- selected threshold: `39000`
- slice index: `380`
- axis: `0`
- foreground voxels: `63757348`
- background voxels: `455362607`
- foreground fraction: `12.281814%`

## Threshold Search

| threshold | rendered SSIM | plot-area IoU | plot-area F1 | slice foreground voxels |
|---:|---:|---:|---:|---:|
| 33000 | 0.842229 | 0.246038 | 0.394912 | 136121 |
| 36000 | 0.928673 | 0.539161 | 0.700591 | 62093 |
| 39000 | 0.968517 | 0.786716 | 0.880628 | 38707 |
| 42000 | 0.965949 | 0.766989 | 0.868131 | 27243 |
| 45000 | 0.955625 | 0.629221 | 0.772420 | 21146 |
| 48000 | 0.947159 | 0.503952 | 0.670170 | 16900 |
| 51000 | 0.939862 | 0.385655 | 0.556639 | 12877 |
| 54000 | 0.932344 | 0.234384 | 0.379759 | 7847 |
| 56000 | 0.926444 | 0.080649 | 0.149261 | 2688 |

## Validation Against `ground_truth_segmentation_slice_380.png`

- rendered SSIM: `0.968517`
- rendered MSE: `198.764069`
- rendered MAE: `1.568066`
- plot-area foreground IoU: `0.786716`
- plot-area foreground F1: `0.880628`
- plot-area precision: `0.821310`
- plot-area recall: `0.949180`
- plot-area accuracy: `0.987334`

## Outputs

- mask TIFF: `data/9x9x9_octet_lattice/9x9x9_octet_lattice_segmentation_threshold_39000.tif`
- slice visualization: `data/9x9x9_octet_lattice/segmentation/segmentation_slice_380.png`
- comparison image: `data/9x9x9_octet_lattice/segmentation/slice_380_comparison.png`
- threshold sweep plot: `data/9x9x9_octet_lattice/segmentation/threshold_sweep_slice_380.png`
- threshold sweep JSON: `data/9x9x9_octet_lattice/segmentation/threshold_sweep_results.json`
- report: `data/9x9x9_octet_lattice/segmentation/SEGMENTATION_REPORT.md`

## Notes

- The optimization loop evaluated 9 thresholds and selected the best one by plot-area foreground IoU on slice 380, using plot-area F1 and rendered-image SSIM as tie-breakers.
- Validation is image-based because the provided reference is a rendered PNG rather than a voxel-aligned mask volume.
