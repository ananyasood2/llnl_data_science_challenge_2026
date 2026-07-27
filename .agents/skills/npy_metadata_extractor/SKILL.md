---
name: npy_metadata_extractor
description: Use this skill when the user asks to inspect a .npy file, summarize NumPy array metadata, or report shape, dtype, min, max, mean, standard deviation, and nonzero voxel count for generated CT, segmentation, or skeleton arrays.
---

# NPY Metadata Extractor

When this skill is active, inspect one or more `.npy` files and report basic NumPy metadata.

## Workflow

1. Identify the requested `.npy` file path. If the user does not provide one, look under `data/` for likely files such as CT volumes, segmentation masks, threshold outputs, or skeleton arrays.
2. Load the array with NumPy.
3. Report:
   - file path
   - shape
   - dtype
   - total voxel count
   - minimum value
   - maximum value
   - mean
   - standard deviation
   - nonzero voxel count
   - nonzero fraction
4. If the array has 10 or fewer unique values, report the unique values too.

Use Python with NumPy to load the file and compute the metadata. Keep the final response concise and include the numerical results.
