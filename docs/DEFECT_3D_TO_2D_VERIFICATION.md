# Defect 3D-to-2D Verification Audit

Status: Phase 1 repository and coordinate-flow audit  
Audit date: 2026-07-28  
Scientific behavior changed in this phase: no

> Current canonical assessment: [STRUT_NODE_VALIDATION.md](STRUT_NODE_VALIDATION.md).
> The detailed text below preserves the first audit snapshot, including a
> temporary invalid-threshold cache state that is no longer current. The
> reproducible current result is
> `outputs/verification/verification_summary.json`.

## Executive finding

The application cannot currently verify that a selected 3D defect corresponds
to the correct location in the original CT volume. The active Dash application
has a mostly consistent internal `ZYX array <-> XYZ voxel` convention, and its
coarse marching-cubes surface restores its local bounding-box offset and
downsampling factors correctly. However, selection stops at a design element
ID: no raw CT slice, segmentation slice, skeleton slice, local crop, coordinate
transform, or threshold-sensitivity evidence is produced.

The active missing-struts cache is also scientifically invalid at the time of
this audit. It was generated with threshold `0.005` for a `uint16` TIFF whose
sampled Otsu threshold is `40127`. The resulting foreground fraction is `1.0`;
all 18,468 struts and 10,206 nodes are classified healthy; all 93 intentional
missing struts are missed. Existing cached classifications must not be treated
as evidence.

## Repository inventory

### Implemented

- Standalone 3D Dash viewer: `app/app.py`
- Dataset configuration: `app/datasets.py`
- TIFF/NPY and JSON loading: `src/lattice_pipeline/io.py`
- Segmentation: `src/lattice_pipeline/segment.py`
- Skeletonization/topology: `src/lattice_pipeline/skeleton.py`
- Graph alignment: `src/lattice_pipeline/align.py`
- Defect rules: `src/lattice_pipeline/defects.py`
- Cache/orchestration: `src/lattice_pipeline/cache.py`
- CAD ID validation and unreliable-face heuristic:
  `src/lattice_pipeline/validation.py`
- Scientific/dashboard tests: `tests/`
- FastAPI health-only scaffold: `services/analysis-api/`
- Next.js landing-page scaffold: `apps/web/`

### Not implemented or absent

- `CT_Lattice_Analysis.ipynb`
- Next.js Lattice Structure page
- Next.js Defect Inspection page
- Frontend API types for analysis or evidence
- FastAPI analysis, defect-evidence, slice, local-volume, or recheck endpoints
- A selected-defect evidence model
- Orthogonal CT evidence views
- Local 3D evidence crops
- Threshold-persistence checks
- Validation-bundle export
- Source files under `src/contracts`, `src/dashboard`, and `src/demo`

The last three directories contain stale Python bytecode only. Bytecode is not
an auditable or maintainable source implementation and is not considered part
of the active application.

`NetworkX` is named in the project description but is not declared in the
repository requirements and is not imported by the active source.

## Current coordinate systems

| Name | Representation | Axis order | Units | Status |
| --- | --- | --- | --- | --- |
| Raw TIFF array | `volume[z, y, x]` | ZYX | native intensity / voxel index | Confirmed by TIFF metadata |
| Analysis arrays | `volume[::2, ::2, ::2]` | ZYX | analysis voxels | Confirmed in cache pipeline |
| Registered JSON | `position=[x,y,z]` | XYZ | assumed original CT voxels | Assumed from file placement/config |
| Aligned graph | `position=[x,y,z] / stride` | XYZ | analysis voxels | Confirmed in cache pipeline |
| Defect classifier | points in XYZ; arrays in ZYX | explicit reversal | analysis voxels | Confirmed in code |
| Serialized graph/defects | XYZ | XYZ | intended original CT voxels | Multiplied by analysis stride |
| Plotly viewer | `x,y,z` | XYZ | original CT voxel indices | Confirmed in trace construction |
| Physical measurements | scalar estimated spacing | XYZ treated isotropically | mm/µm | Not verified |

No canonical typed `VoxelCoordinate`, `PhysicalCoordinate`, or complete
`CoordinateTransform` currently exists.

## Raw volume axis order

The current missing-struts TIFF reports:

- shape: `(761, 815, 837)`
- axes: `ZYX`
- dtype: `uint16`
- X extent: indices `0..836`
- Y extent: indices `0..814`
- Z extent: indices `0..760`

Therefore the mathematically correct orthogonal slices are:

```python
xy = volume[z, :, :]  # horizontal x, vertical y
xz = volume[:, y, :]  # horizontal x, vertical z
yz = volume[:, :, x]  # horizontal y, vertical z
```

No active view renders these slices, so image-origin orientation and crosshair
placement are not yet verified.

NPY inputs are also interpreted as ZYX, but NPY files carry no named-axis
metadata and the loader does not validate that assumption.

## Current end-to-end coordinate pipeline

### 1. Loading and segmentation

```text
TIFF series: raw[z, y, x]
    |
    | stride = 2
    v
analysis[z_a, y_a, x_a] = raw[2*z_a, 2*y_a, 2*x_a]
```

No scientific crop is applied.

### 2. Registered design graph

The configured graph position is treated as original voxel XYZ:

```text
json_xyz_original
    |
    | divide by analysis_stride
    v
json_xyz_analysis
    |
    | optional robust affine refinement to downsampled skeleton
    v
aligned_xyz_analysis
```

The classifier samples in XYZ and accesses arrays using:

```python
mask[z, y, x]
```

Skeleton coordinates are created with `argwhere`, which returns ZYX, and are
explicitly reversed to XYZ.

### 3. Result restoration

Nodes, strut polylines, and defect locations are multiplied by the analysis
stride:

```text
original_xyz = analysis_xyz * 2
slice_index = round(analysis_z) * 2
```

This restoration does not account for crop offsets because no scientific crop
exists.

### 4. Coarse 3D CT surface

The mask is cropped to its foreground bounding box in analysis ZYX. It is then
subsampled by `surface_step`, currently about 9–10. Marching cubes returns local
ZYX vertices. The viewer restores them with:

```text
analysis_zyx = local_surface_zyx * surface_step + bbox_min_zyx
original_zyx = analysis_zyx * analysis_stride
display_xyz = reverse(original_zyx)
```

This formula correctly reverses the display crop and both display sampling
factors. The transform and crop are not retained as metadata, and there is no
surface-click-to-original-voxel implementation.

## Crop and excluded-region audit

No crop configuration is present in `app/datasets.py`.

At the valid sampled Otsu threshold, the downsampled foreground bounding box
maps to approximately:

```text
x: 18..782
y: 24..766
z: 0..760
```

Y planes above approximately `766` contain no thresholded foreground even
though the raw array continues through Y index `814`. This supports the
interpretation that the high-Y side is cut, absent, or outside the useful
analysis object. The pipeline does not encode this as an exclusion region.

The manual axis-maximum controls affect Plotly visibility and visible counts
only. They do not alter segmentation, skeletonization, endpoint detection, or
defect classification.

The existing unreliable-face heuristic can downgrade a face when most of its
design struts appear absent. It does not provide:

- original/cropped coordinate transforms;
- an explicit cut-region mask;
- distance to the analysis boundary;
- a configurable boundary buffer;
- protection when the threshold is degenerate;
- exclusion metadata for selected candidates.

The classifier's `_near_crop` check uses the full downsampled array bounds, not
the observed object/cut boundary. Crop-created endpoints can therefore still be
reported as broken / disconnected unless another heuristic catches them.

## Downsampling audit

`analysis_stride=2` is used for segmentation, skeletonization, distance
transform, registration refinement, and final defect classification. It is not
display-only.

The coarse viewer adds a second sampling factor of roughly 9–10 after taking a
foreground bounding-box crop. The viewer reverses that sampling for mesh
coordinates, but scientific classifications remain based on half-resolution
data.

This violates the requested policy that display downsampling must not become
the final evidence resolution unless a separately validated multiresolution
method exists. No such validation currently exists.

## Physical-coordinate audit

The TIFF has no X/Y resolution tags and no ImageJ Z spacing. Physical voxel
spacing is unavailable from source metadata.

The application currently supplies an estimated isotropic value:

```text
0.057738 mm = 57.738 µm per voxel
```

It is inferred from the nominal 9 × 4.56 mm design span. The cache marks this as
`user_override` when the Dash app passes the configured value explicitly.

Consequences:

- anisotropy cannot be excluded;
- physical coordinates are estimates, not measurements;
- 350 µm thickness comparisons are not verified;
- current thin/thick classifications are unsupported under the required
  evidence standard.

Until spacing is explicitly verified, physical coordinate and thickness fields
should be nullable and accompanied by a warning.

## JSON-to-CT registration audit

The configured TIFF and registered JSON share the same specimen basename:

```text
210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices
```

This supports sample pairing, but the code does not enforce the basename match.

The JSON provides no registration metadata, units, axis order, transform,
sample ID, or verification status. Its XYZ bounding box fits inside the CT:

```text
min XYZ = [58.76, 48.57, 24.50]
max XYZ = [773.74, 764.94, 737.85]
```

Configuration forces identity registration. The only mandatory runtime check
is that graph coordinates fit inside the volume.

With a valid threshold, robust skeleton refinement changes graph coordinates
and improves measured registration:

```text
median node-to-skeleton distance before: about 1.99 original voxels
median node-to-skeleton distance after:  about 1.34 original voxels
p90 before: about 5.37 original voxels
p90 after:  about 3.29 original voxels
```

This is useful measured evidence, but it is not independent: the transform is
fit to the thresholded skeleton later used for classification. It can also fail
silently when thresholding is degenerate. The configured CAD cube symmetry has
no source/provenance record.

Current registration status should therefore be:

```text
supported / registration not independently verified
```

Design-based missing-strut claims must be disabled whenever registration
quality, sample pairing, or coordinate metadata fails.

## Defect-to-slice selection logic

There is no implemented selected-defect slice flow.

For a generated defect record:

- missing-strut location is a sampled graph point selected using skeleton
  distance;
- broken / disconnected location is a nearby internal skeleton endpoint or
  secondary-component path;
- thin/thick location defaults to the expected edge midpoint;
- node location is the aligned graph node;
- `slice_index` is rounded Z in the current analysis coordinates and later
  multiplied by stride.

The 3D viewer renders entire expected graph polylines. Clicking one returns its
element ID and classification, not the defect record's evidence location.
Consequently a future UI that uses the line midpoint or clicked Plotly point
without an explicit transform could open the wrong raw slice.

## Classification support audit

### Active cached state

The current cache request is:

```text
threshold = 0.005
TIFF dtype = uint16
sampled Otsu = 40127
foreground fraction = 1.0
```

Current cached output:

```text
healthy struts = 18,468
healthy nodes = 10,206
detected defects = 0
expected intentional missing struts = 93
false negatives against CAD IDs = 93
```

This result is contradicted by explicit design ground truth.

### Evidence status by class

| Classification | Current evidence status | Reason |
| --- | --- | --- |
| Missing strut | Contradicted in active cache | Invalid threshold misses all 93 CAD removals |
| Missing node | Contradicted/incomplete | Invalid cache reports none; node semantics need explicit definition |
| Broken / disconnected strut | Questionable | Internal skeleton endpoint or secondary-component rule only; no crop-boundary exclusion |
| Thin/thick strut | Unsupported | Physical spacing is estimated and anisotropy unknown |
| Boundary uncertain | Rule-based interpretation | Heuristic face downgrade, no explicit cut-region model |
| Severity/rule strength | Uncalibrated decision-margin output; null for healthy elements | No empirical calibration or evidence-status model |

Earlier valid-threshold aggregate CAD metrics are encouraging, but they do not
verify every displayed candidate against raw CT, mask, skeleton, graph,
exclusion metadata, and threshold persistence. They must be described as
supported rather than verified.

## Measured evidence, rules, interpretation, and uncertainty

The repaired system must keep these categories separate:

- **Measured evidence:** raw intensity statistics, mask occupancy, skeleton
  distance/connectivity, graph-tube occupancy, boundary distance, and
  measurements at each tested threshold.
- **Rule-based classification:** deterministic cutoffs and the decision table.
- **Interpretation:** missing, broken / disconnected, thin, threshold artifact,
  skeleton artifact, registration problem, or boundary-created endpoint.
- **Uncertainty:** missing spacing, unverified registration, threshold
  sensitivity, crop proximity, low resolution, and conflicting signals.

The current serialized result mixes these categories.

## Bugs and correctness gaps found

1. No selected 3D candidate can be traced to original CT slices.
2. No canonical typed coordinate/transform model exists.
3. No orthogonal-slice marker tests exist.
4. No image-origin convention is defined.
5. No scientific crop or excluded cut-region metadata exists.
6. Full-array bounds are incorrectly used as crop-boundary evidence.
7. Final classification uses downsampled data.
8. Physical spacing is unavailable but physical thickness is still classified.
9. Registered JSON is trusted by configuration and in-bounds fit alone.
10. Registration refinement is segmentation-dependent and can be skipped by a
    bad threshold.
11. Threshold input is not validated against native data range or foreground
    fraction.
12. The active cache is invalid and contradicted by the 93-strut CAD ground
    truth.
13. No raw CT, segmentation, skeleton, graph, or threshold evidence object
    exists per candidate.
14. No deterministic conflict/uncertainty decision table is implemented.
15. No analysis endpoints or frontend analysis pages/types exist.
16. The frontend test command executes zero tests.
17. The named exploratory notebook is absent.

## Proposed repair files

### Phase 2: canonical coordinates and mathematical tests

- Add `src/lattice_pipeline/coordinates.py`.
- Add `tests/test_coordinates.py`.
- Update `src/lattice_pipeline/__init__.py`.

### Phase 3: evidence extraction

- Add `src/lattice_pipeline/evidence.py`.
- Add `tests/test_evidence.py`.
- Update `src/lattice_pipeline/io.py` and `cache.py`.
- Update `app/datasets.py` with explicit crop, exclusion, spacing, and
  registration metadata.

### Phase 4: evidence-gated classification

- Update `src/lattice_pipeline/defects.py`, `align.py`, and `validation.py`.
- Add healthy, broken / disconnected, segmentation-artifact, skeleton-artifact,
  crop-boundary, and registration-error tests.

### Phase 5: API and UI

- Add FastAPI evidence schemas and routes under
  `services/analysis-api/app/`.
- Add API adapter and endpoint tests.
- Add Next.js Lattice Structure and Defect Inspection routes, components,
  generated/validated types, and frontend tests.
- Update the Dash app only where needed for the developer validation view and
  synchronized selection.

### Phase 6: real-data validation and bundles

- Add developer validation script/view.
- Add bounded validation-bundle export.
- Finalize this document and `outputs/verification/verification_summary.json`.

## Required mathematical tests

The repair plan includes all requested synthetic cases:

1. landmark at `(x=7,y=11,z=15)` in XY/XZ/YZ;
2. crop offset round trip;
3. display downsampling inversion;
4. crop plus downsampling;
5. axis permutation detection;
6. axis flip detection;
7. healthy strut;
8. internal broken / disconnected strut;
9. threshold/segmentation artifact;
10. skeleton-only interruption;
11. crop-boundary endpoint;
12. translated/unverified graph.

## Baseline checks

Run on 2026-07-28:

- Scientific/dashboard Python tests: 23 passed.
- FastAPI tests: 2 passed.
- Frontend lint: passed.
- Frontend type check: passed.
- Frontend test command: passed but discovered zero tests.
- Frontend production build: passed outside the restricted sandbox. The first
  sandboxed attempt failed because Turbopack was not permitted to bind a local
  helper port, not because of a source/build error.

These tests establish regression health only. They do not satisfy the
coordinate/evidence acceptance criteria.

## Screenshots

No before/after 2D evidence screenshots can be produced in Phase 1 because the
orthogonal evidence view does not exist. This absence is a verified finding.
Phase 3 must produce synthetic landmark screenshots; Phase 6 must add bounded
real-candidate before/after evidence images without committing large CT data.

## Candidates whose classifications changed

None in Phase 1. This phase intentionally made no scientific changes.

The current cache itself changed before this audit to an invalid `0.005`
threshold and now reports zero defects. That external/current-state change is
recorded as a baseline failure, not presented as a Phase 1 repair.

## Remaining uncertainties

- Exact physical voxel spacing and anisotropy.
- Independent provenance and accuracy of registered JSON coordinates.
- Provenance of the configured CAD cube symmetry.
- Exact intended high-Y cut/exclusion bounds and required safety buffer.
- Candidate-level threshold persistence.
- Full-resolution CT support for every current missing and broken / disconnected
  prediction.
- Definitions and ground truth for a “missing node.”

No defect should be called verified until those applicable uncertainties are
resolved with ground truth or explicit matching metadata.
