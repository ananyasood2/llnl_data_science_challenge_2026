"""Canonical transforms between graph, physical, and NumPy coordinates.

The public graph/physical convention is always ``(x, y, z)``. NumPy arrays
remain indexed ``(z, y, x)``.  This module is deliberately independent of the
detector so coordinate provenance can be validated before any defect rule is
allowed to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

import numpy as np

RegistrationStatus = Literal[
    "verified",
    "likely_valid",
    "registration_warning",
    "registration_failed",
]


def _triplet(
    value: Sequence[Any],
    *,
    name: str,
    dtype: type = float,
) -> np.ndarray:
    result = np.asarray(value, dtype=dtype)
    if result.shape != (3,):
        raise ValueError(f"{name} must contain exactly three values")
    return result


def _points_xyz(value: Any, *, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape[-1:] != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must end in three finite XYZ coordinates")
    return result


@dataclass(frozen=True)
class CoordinateTransform:
    """Explicit JSON-XYZ to CT-voxel transform.

    ``axis_permutation`` states which JSON component supplies each physical
    XYZ component. ``axis_directions`` stores axis flips as ``+1`` or ``-1``.
    Scale and translation map the permuted/signed JSON values into physical
    coordinates. CT voxel conversion then uses physical origin and voxel
    spacing. ``crop_offset_zyx`` is only applied when ``cropped=True`` so full
    volume coordinates remain the default and are never silently discarded.
    """

    transform_id: str
    axis_permutation: tuple[int, int, int] = (0, 1, 2)
    axis_directions: tuple[int, int, int] = (1, 1, 1)
    json_scale_to_physical_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0)
    translation_physical_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    voxel_spacing_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0)
    voxel_origin_physical_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    crop_offset_zyx: tuple[float, float, float] = (0.0, 0.0, 0.0)
    physical_units: str = "um"
    registration_status: RegistrationStatus = "registration_warning"

    def __post_init__(self) -> None:
        if not self.transform_id.strip():
            raise ValueError("transform_id must not be empty")
        permutation = _triplet(
            self.axis_permutation,
            name="axis_permutation",
            dtype=int,
        )
        if sorted(permutation.tolist()) != [0, 1, 2]:
            raise ValueError("axis_permutation must be a permutation of (0, 1, 2)")
        directions = _triplet(
            self.axis_directions,
            name="axis_directions",
            dtype=int,
        )
        if not np.all(np.isin(directions, (-1, 1))):
            raise ValueError("axis_directions values must be +1 or -1")
        scale = _triplet(
            self.json_scale_to_physical_xyz,
            name="json_scale_to_physical_xyz",
        )
        spacing = _triplet(self.voxel_spacing_xyz, name="voxel_spacing_xyz")
        for name, values in (
            ("json_scale_to_physical_xyz", scale),
            ("voxel_spacing_xyz", spacing),
        ):
            if np.any(~np.isfinite(values)) or np.any(values <= 0):
                raise ValueError(f"{name} values must be positive and finite")
        for name, values in (
            ("translation_physical_xyz", self.translation_physical_xyz),
            ("voxel_origin_physical_xyz", self.voxel_origin_physical_xyz),
            ("crop_offset_zyx", self.crop_offset_zyx),
        ):
            if np.any(~np.isfinite(_triplet(values, name=name))):
                raise ValueError(f"{name} values must be finite")
        if self.registration_status not in {
            "verified",
            "likely_valid",
            "registration_warning",
            "registration_failed",
        }:
            raise ValueError(f"Unknown registration_status {self.registration_status!r}")

    def json_xyz_to_physical_xyz(self, json_xyz: Any) -> np.ndarray:
        points = _points_xyz(json_xyz, name="json_xyz")
        mapped = points[..., list(self.axis_permutation)]
        return (
            mapped
            * np.asarray(self.axis_directions, dtype=float)
            * np.asarray(self.json_scale_to_physical_xyz, dtype=float)
            + np.asarray(self.translation_physical_xyz, dtype=float)
        )

    def physical_xyz_to_voxel_zyx(
        self,
        physical_xyz: Any,
        *,
        cropped: bool = False,
    ) -> np.ndarray:
        points = _points_xyz(physical_xyz, name="physical_xyz")
        voxel_xyz = (
            points - np.asarray(self.voxel_origin_physical_xyz, dtype=float)
        ) / np.asarray(self.voxel_spacing_xyz, dtype=float)
        voxel_zyx = voxel_xyz[..., ::-1]
        if cropped:
            voxel_zyx = voxel_zyx - np.asarray(self.crop_offset_zyx, dtype=float)
        return voxel_zyx

    def voxel_zyx_to_physical_xyz(
        self,
        voxel_zyx: Any,
        *,
        cropped: bool = False,
    ) -> np.ndarray:
        points = _points_xyz(voxel_zyx, name="voxel_zyx")
        if cropped:
            points = points + np.asarray(self.crop_offset_zyx, dtype=float)
        voxel_xyz = points[..., ::-1]
        return (
            voxel_xyz * np.asarray(self.voxel_spacing_xyz, dtype=float)
            + np.asarray(self.voxel_origin_physical_xyz, dtype=float)
        )

    def json_strut_to_voxel_endpoints(
        self,
        start_json_xyz: Any,
        end_json_xyz: Any,
        *,
        cropped: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        endpoints = _points_xyz(
            [start_json_xyz, end_json_xyz],
            name="JSON strut endpoints",
        )
        physical = self.json_xyz_to_physical_xyz(endpoints)
        voxel = self.physical_xyz_to_voxel_zyx(physical, cropped=cropped)
        return voxel[0], voxel[1]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "transform_id": self.transform_id,
            "axis_permutation": list(self.axis_permutation),
            "axis_directions": list(self.axis_directions),
            "json_scale_to_physical_xyz": list(
                self.json_scale_to_physical_xyz
            ),
            "translation_physical_xyz": list(self.translation_physical_xyz),
            "voxel_spacing_xyz": list(self.voxel_spacing_xyz),
            "voxel_origin_physical_xyz": list(
                self.voxel_origin_physical_xyz
            ),
            "crop_offset_zyx": list(self.crop_offset_zyx),
            "physical_units": self.physical_units,
            "registration_status": self.registration_status,
            "array_axis_order": "zyx",
            "graph_axis_order": "xyz",
        }

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "CoordinateTransform":
        return cls(
            transform_id=str(metadata["transform_id"]),
            axis_permutation=tuple(metadata.get("axis_permutation", (0, 1, 2))),
            axis_directions=tuple(metadata.get("axis_directions", (1, 1, 1))),
            json_scale_to_physical_xyz=tuple(
                metadata.get("json_scale_to_physical_xyz", (1.0, 1.0, 1.0))
            ),
            translation_physical_xyz=tuple(
                metadata.get("translation_physical_xyz", (0.0, 0.0, 0.0))
            ),
            voxel_spacing_xyz=tuple(
                metadata.get("voxel_spacing_xyz", (1.0, 1.0, 1.0))
            ),
            voxel_origin_physical_xyz=tuple(
                metadata.get("voxel_origin_physical_xyz", (0.0, 0.0, 0.0))
            ),
            crop_offset_zyx=tuple(
                metadata.get("crop_offset_zyx", (0.0, 0.0, 0.0))
            ),
            physical_units=str(metadata.get("physical_units", "um")),
            registration_status=metadata.get(
                "registration_status",
                "registration_warning",
            ),
        )


def json_xyz_to_physical_xyz(
    json_xyz: Any,
    transform: CoordinateTransform,
) -> np.ndarray:
    return transform.json_xyz_to_physical_xyz(json_xyz)


def physical_xyz_to_voxel_zyx(
    physical_xyz: Any,
    transform: CoordinateTransform,
    *,
    cropped: bool = False,
) -> np.ndarray:
    return transform.physical_xyz_to_voxel_zyx(physical_xyz, cropped=cropped)


def voxel_zyx_to_physical_xyz(
    voxel_zyx: Any,
    transform: CoordinateTransform,
    *,
    cropped: bool = False,
) -> np.ndarray:
    return transform.voxel_zyx_to_physical_xyz(voxel_zyx, cropped=cropped)


def json_strut_to_voxel_endpoints(
    start_json_xyz: Any,
    end_json_xyz: Any,
    transform: CoordinateTransform,
    *,
    cropped: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    return transform.json_strut_to_voxel_endpoints(
        start_json_xyz,
        end_json_xyz,
        cropped=cropped,
    )


__all__ = [
    "CoordinateTransform",
    "RegistrationStatus",
    "json_strut_to_voxel_endpoints",
    "json_xyz_to_physical_xyz",
    "physical_xyz_to_voxel_zyx",
    "voxel_zyx_to_physical_xyz",
]
