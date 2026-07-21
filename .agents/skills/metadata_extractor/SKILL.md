---
name: metadata-extractor
description: Loads a .npy file and reports its shape, dtype, min, max, and mean to the terminal.
---

# Metadata Extraction Protocol

You are the **Metadata Extractor**. When this skill is active, follow these steps:

### Step 1: Locate the Target File
- Identify the `.npy` file the user wants inspected. If the user gave a path, use it directly.
- If the user only gave a directory (e.g. "check the files in ./data"), list all `.npy` files there and run this process on each one.

### Step 2: Extract Metadata
Invoke the `extract_metadata` script (in the `./scripts` subdirectory of this skill) on the target file. It reports:
- Shape
- Data type (dtype)
- Minimum value
- Maximum value
- Mean value

### Step 3: Report to Terminal
Print the results in a clear, labeled format for each file processed. Do not write this to a report file — this skill's output is terminal-only, matching its stated purpose.

# Technical Constraints
- If the file cannot be loaded (corrupted, wrong format, or not found), report a clear error instead of stopping silently.
- Look for `extract_metadata.py` in the `./scripts` subdirectory of this skill.
- If you created any additional python scripts beyond the provided one, remove them once you are finished.