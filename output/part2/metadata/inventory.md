# Missing-Strut Dataset Inventory

## Inventory

- Dataset: `data/missing_struts`
- File counts: .json: 2, .stl: 4, .tif: 1, .txt: 1
- TIFF stacks present: 1
- Graph JSON files: 2
- STL designs: 4

## Variants

| Nominal missing struts | TIFF stacks present | STL designs |
|---|---:|---:|
| 0% | 0 | 1 |
| 0.1% | 0 | 1 |
| 0.5% | 1 | 1 |
| 1% | 0 | 1 |

## CT Stacks

| File | Shape (z, y, x) | Dtype | Nominal |
|---|---|---|---|
| `data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif` | (761, 815, 837) | uint16 | 0.5% |

## Registration

Only registered_pairs may be compared directly in CT voxel coordinates. All other CT/design comparisons require an explicit registration stage.

- Registered: `data/missing_struts/tif_stacks/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif` <-> `data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json`.
- Not registered graph `data/missing_struts/octet_truss_9x9x9.json`: 10206 junctions, 18468 struts.
- Registered graph `data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json`: 10206 junctions, 18468 struts.

## Literature Grounding

Tran et al. (2023), Resonant ultrasound spectroscopy measurement and modeling of additively manufactured octet truss lattice cubes, NDT & E International 138, 102870.

Primary source: https://doi.org/10.1016/j.ndteint.2023.102870

Treat missing and disconnected struts as mutually exclusive classes. The paper reports measured missing-strut percentages above nominal and disconnected-strut rates near 5% (with specimen-level variation); use nominal percentages as design labels rather than a strict measured target.

## Caveats

- The repository currently contains one TIFF stack, although file_names.txt documents additional scan names.
- The 0.1% STL exists but has no matching scan listed in file_names.txt.
- File names encode nominal design intent, not CT-measured defect counts.
