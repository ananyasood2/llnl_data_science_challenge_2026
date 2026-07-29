# Registered Lattice CT NDE Screening Report

## Result

| class | struts | percent |
|---|---:|---:|
| present | 16493 | 89.306% |
| missing | 872 | 4.722% |
| disconnected | 1103 | 5.972% |
| flagged | 1975 | 10.694% |
| total | 18468 | 100.000% |

## Parameters

- Selected intensity threshold: 37026 (bounded candidate score 0.947504; all candidates: `threshold_search_results.csv`).
- Downsampling: 4 applied identically to CT and registered graph after XYZ→ZYX conversion.
- Small-component removal: <100 downsampled voxels. Trim: 12% each endpoint. Coverage: within 4.0 original CT voxels.
- Verdict rules: missing <0.25 coverage; disconnected otherwise when longest uncovered run >0.12; present otherwise.
- Sensitivity: radii 2/3/4 and missing thresholds .25/.30/.35 recorded in `sensitivity_study.csv`; selected r=4 and .25 as the most conservative false-positive-resistant setting.

## Limitations

These are image-derived screening labels, not confirmed physical defects. Only the registered JSON graph was used; no unregistered STL geometry was compared to CT. Registration uncertainty, segmentation, downsampling, and CT artifacts remain possible sources of error.
