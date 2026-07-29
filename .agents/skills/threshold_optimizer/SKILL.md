---
name: threshold-optimizer
description: Compare thresholded CT masks and select a traceable candidate for lattice segmentation.
---

# Threshold Optimizer

For an input `.npy` CT volume, call `segment_ct_dataset` at three or more thresholds spanning the data range. Call `visualize_slice` on the same central slice for each candidate, save outputs under `output/threshold_optimizer/`, and compare foreground fraction and visible strut continuity. Record the selected threshold, alternatives, and reason in `selection.md`. Do not overwrite source data.
