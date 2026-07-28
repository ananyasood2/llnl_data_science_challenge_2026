# API Contracts

FastAPI Pydantic schemas and the exported OpenAPI document will become the
contract source of truth in Phase 2.

## Contract policy

- Scientific units are explicit in field names.
- Unavailable values are nullable; missing data is not converted to zero.
- Large arrays never appear in normal JSON responses.
- Every mock response identifies demo mode.
- Contract changes require team discussion and regenerated TypeScript types.
- Phase 2 will create the generated-types location and command together; generated
  files will not be edited manually.

## Planned versioned resources

- system configuration and health
- datasets and upload metadata
- analysis summaries and jobs
- grounded chat requests/responses
- report retrieval

The detailed field inventory from the project brief will be implemented and
tested in Phase 2. Until then, `/health` is the only stable public endpoint.

## Proposed dataset slice preview contract

Dataset intake currently validates uploaded files and returns compact metadata,
but it does not persist a dataset record or return a stable dataset ID. A slice
preview endpoint therefore depends on first adding a dataset creation/storage
step that returns `dataset_id` and asset references.

Once a stable dataset ID exists, the preferred image contract is:

```text
GET /v1/datasets/{dataset_id}/slices/{axis}/{index}?view=original|segmentation|skeleton
```

Path and query values:

- `dataset_id`: opaque stable dataset identifier returned by dataset creation.
- `axis`: `x`, `y`, or `z`.
- `index`: zero-based slice index along that axis.
- `view`: `original`, `segmentation`, or `skeleton`.

Successful image response:

- `200 OK`
- `Content-Type: image/png`
- body is the rendered PNG slice, not JSON pixel data.
- optional headers may include `X-Voxel-Size-Micron`,
  `X-Slice-Index`, `X-Slice-Axis`, and `X-View`.

Alternative URI response, useful when slices are pre-rendered to object storage:

```json
{
  "dataset_id": "opaque-dataset-id",
  "axis": "z",
  "index": 128,
  "view": "original",
  "image_uri": "https://storage.example/signed-or-public-slice.png",
  "width_px": 470,
  "height_px": 470,
  "voxel_size_micron": null,
  "expires_at": "2026-07-27T20:00:00Z",
  "demo_mode": false
}
```

Unavailable generated views should not fall back to synthetic images:

- `404 Not Found` when the dataset exists but the requested segmentation or
  skeleton artifact has not been generated.
- `409 Conflict` is also acceptable if the API wants to distinguish “known
  dataset, missing pipeline stage” from missing routes or missing datasets.

Large arrays must not appear in JSON responses. Unknown units or dimensions stay
nullable rather than being converted to zero.
