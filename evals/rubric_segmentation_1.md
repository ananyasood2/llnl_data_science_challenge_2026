# Segmentation Evaluation Rubric

Compare the result image against the ground truth segmentation slice.

## Criteria

1. Structural Integrity
   - Does the result capture the connectivity of the lattice struts compared to the ground truth?

2. False Positives / Negatives
   - Check for over-segmentation, extra noise, or under-segmentation, missing struts.

3. Topology
   - Are the nodes and junctions preserved?

4. Noise and Artifacts
   - Does the result contain noise or artifacts not present in the ground truth?

## Scoring

- 5: Identical to ground truth. No missing structures, no false positives.
- 4: Excellent with very minor differences.
- 3: Main topology is correct, but noticeable noise or thin struts are missing.
- 2: Fair, but with significant differences such as large chunks missing.
- 1: Major structural failure or excessive noise.
- 0: Blank or unrelated output.

## Output Format

Return only JSON with:
- `reasoning`
- `score`