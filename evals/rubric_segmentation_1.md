# Segmentation Result Evaluation Rubric

Compare the first attached image (ground truth) with the second attached image (segmentation result).

Score all criteria together on a 0-5 scale:

1. **Structural integrity:** Does the result preserve lattice-strut connectivity?
2. **False positives and negatives:** Identify extra noise/over-segmentation and missing struts/under-segmentation.
3. **Topology:** Are junction nodes preserved in the correct locations?
4. **Noise and artifacts:** Does the result add artifacts absent from the clean ground truth?

Score definitions:

- `5`: Identical to ground truth; no missing structures or false positives.
- `4`: Excellent; only very minor differences.
- `3`: Main topology is correct, with noticeable noise or missing thin struts.
- `2`: Fair; significant differences such as large missing regions.
- `1`: Major structural failure or excessive noise.
- `0`: Blank or unrelated output.

Return **only** this JSON object, with no Markdown fence:

```json
{"reasoning":"concise comparison tied to the four criteria","score":0}
```
