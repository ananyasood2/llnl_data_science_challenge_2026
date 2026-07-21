---
name: threshold-optimizer
description: Segments a CT dataset at multiple threshold values derived from the data's own distribution, saving each result separately for comparison.
---

# Threshold Optimization Protocol

You are the **Threshold Optimizer**. When this skill is active, follow these steps:

### Step 1: Determine Candidate Thresholds
- Load the target raw `.npy` file directly (not through an MCP tool) to inspect its value distribution.
- Do NOT assume the data range is [0, 1]. Compute the actual min, max, and the 75th, 90th, and 95th percentiles of the data.
- Use these three percentile values as your candidate thresholds. This adapts to whatever range the specific file actually has, rather than relying on fixed guesses.

### Step 2: Run Segmentation at Each Threshold
For each candidate threshold, call the `segment_ct_dataset` MCP tool with that threshold value. Save each output to a separate file, named to indicate which threshold produced it (e.g. `<original_name>_seg_p75.npy`, `_seg_p90.npy`, `_seg_p95.npy`).

### Step 3: Compare Results
For each segmented output, report:
- The threshold value used
- The resulting foreground voxel count (sum of the mask)
- The foreground voxel count as a percentage of total voxels

Present this as a simple comparison table so the user can see how the segmented volume shrinks as the threshold increases.

### Step 4: Flag Degenerate Results
If any result is entirely zero (empty) or entirely one (fills the whole volume), flag it explicitly as likely unusable, rather than presenting it as a normal result alongside the others.

# Technical Constraints
- Ensure the input `.npy` array is 3-dimensional before processing.
- Use the `segment_ct_dataset` MCP tool for all segmentation calls — do not reimplement thresholding logic directly in this skill.
- If you created any python scripts to compute percentiles, remove them once you are finished.