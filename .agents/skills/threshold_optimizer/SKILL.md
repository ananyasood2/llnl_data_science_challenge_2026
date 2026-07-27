---
name: threshold_optimizer
description: Use this skill when the user asks to compare segmentation thresholds, optimize CT segmentation, run segment_ct_dataset with multiple threshold values, or choose a good threshold for a volumetric .npy dataset.
---

# Threshold Optimizer

When this skill is active, compare several segmentation thresholds for a CT `.npy` volume and summarize which threshold gives the most useful mask.

## Workflow

1. Identify the input CT volume path. If the user does not provide one, look for likely files under `data/`, such as `data/unitcell/unitcell.npy`.
2. Choose threshold values to test. If the user does not specify values, use:
   - `0.003`
   - `0.005`
   - `0.007`
3. For each threshold, call the MCP tool `segment_ct_dataset()` using:
   - the same input CT file
   - a separate output path for each threshold
   - the current threshold value

Use output filenames like:

```text
data/unitcell/segmentation_threshold_0.003.npy
data/unitcell/segmentation_threshold_0.005.npy
data/unitcell/segmentation_threshold_0.007.npy