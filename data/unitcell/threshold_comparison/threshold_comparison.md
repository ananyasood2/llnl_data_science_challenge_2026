# Threshold comparison for data/unitcell/unitcell.npy

- shape: (256, 256, 256)
- dtype: float32
- min: -0.00312875002
- max: 0.015257692
- mean: 0.000539066852
- std: 0.0024182403

| threshold | foreground voxels | background voxels | foreground fraction | output |
|---:|---:|---:|---:|---|
| 0.0005 | 1887582 | 14889634 | 11.250865% | `data/unitcell/threshold_comparison/segmentation_threshold_0.0005.npy` |
| 0.001 | 1043622 | 15733594 | 6.220472% | `data/unitcell/threshold_comparison/segmentation_threshold_0.001.npy` |
| 0.0025 | 811184 | 15966032 | 4.835033% | `data/unitcell/threshold_comparison/segmentation_threshold_0.0025.npy` |
| 0.005 | 721774 | 16055442 | 4.302108% | `data/unitcell/threshold_comparison/segmentation_threshold_0.005.npy` |
| 0.0075 | 705794 | 16071422 | 4.206860% | `data/unitcell/threshold_comparison/segmentation_threshold_0.0075.npy` |
| 0.01 | 622182 | 16155034 | 3.708494% | `data/unitcell/threshold_comparison/segmentation_threshold_0.01.npy` |
| 0.012 | 403448 | 16373768 | 2.404737% | `data/unitcell/threshold_comparison/segmentation_threshold_0.012.npy` |
