from __future__ import annotations

import numpy as np
import pytest

from lattice_pipeline.coordinates import CoordinateTransform


def test_json_xyz_maps_to_numpy_zyx_and_round_trips_physical_space() -> None:
    transform = CoordinateTransform(
        transform_id="synthetic-isotropic",
        json_scale_to_physical_xyz=(10.0, 10.0, 10.0),
        voxel_spacing_xyz=(10.0, 10.0, 10.0),
        registration_status="verified",
    )

    physical_xyz = transform.json_xyz_to_physical_xyz([7, 11, 15])
    voxel_zyx = transform.physical_xyz_to_voxel_zyx(physical_xyz)

    np.testing.assert_allclose(physical_xyz, [70, 110, 150])
    np.testing.assert_allclose(voxel_zyx, [15, 11, 7])
    np.testing.assert_allclose(
        transform.voxel_zyx_to_physical_xyz(voxel_zyx),
        physical_xyz,
    )


def test_crop_offset_is_explicit_and_full_volume_is_the_default() -> None:
    transform = CoordinateTransform(
        transform_id="cropped",
        voxel_spacing_xyz=(2.0, 3.0, 5.0),
        voxel_origin_physical_xyz=(100.0, 200.0, 300.0),
        crop_offset_zyx=(10.0, 20.0, 30.0),
    )
    physical_xyz = np.asarray([180.0, 290.0, 500.0])

    full_zyx = transform.physical_xyz_to_voxel_zyx(physical_xyz)
    cropped_zyx = transform.physical_xyz_to_voxel_zyx(
        physical_xyz,
        cropped=True,
    )

    np.testing.assert_allclose(full_zyx, [40, 30, 40])
    np.testing.assert_allclose(cropped_zyx, [30, 10, 10])
    np.testing.assert_allclose(
        transform.voxel_zyx_to_physical_xyz(cropped_zyx, cropped=True),
        physical_xyz,
    )


def test_axis_permutation_flip_scale_and_translation_are_not_implicit() -> None:
    transform = CoordinateTransform(
        transform_id="permuted-flipped",
        axis_permutation=(2, 1, 0),
        axis_directions=(-1, 1, 1),
        json_scale_to_physical_xyz=(2.0, 3.0, 4.0),
        translation_physical_xyz=(100.0, 10.0, -5.0),
        voxel_spacing_xyz=(2.0, 3.0, 4.0),
    )

    physical = transform.json_xyz_to_physical_xyz([1.0, 2.0, 3.0])
    voxel = transform.physical_xyz_to_voxel_zyx(physical)

    np.testing.assert_allclose(physical, [94.0, 16.0, -1.0])
    np.testing.assert_allclose(voxel, [-0.25, 16.0 / 3.0, 47.0])


def test_strut_endpoint_conversion_preserves_endpoint_identity() -> None:
    transform = CoordinateTransform(
        transform_id="strut",
        json_scale_to_physical_xyz=(5.0, 5.0, 5.0),
        voxel_spacing_xyz=(5.0, 5.0, 5.0),
    )

    start_zyx, end_zyx = transform.json_strut_to_voxel_endpoints(
        [2, 3, 4],
        [8, 9, 10],
    )

    np.testing.assert_allclose(start_zyx, [4, 3, 2])
    np.testing.assert_allclose(end_zyx, [10, 9, 8])


def test_transform_metadata_round_trip_is_lossless() -> None:
    transform = CoordinateTransform(
        transform_id="metadata",
        axis_permutation=(1, 2, 0),
        axis_directions=(1, -1, 1),
        json_scale_to_physical_xyz=(1.5, 2.5, 3.5),
        translation_physical_xyz=(4.0, 5.0, 6.0),
        voxel_spacing_xyz=(0.5, 0.75, 1.25),
        voxel_origin_physical_xyz=(10.0, 20.0, 30.0),
        crop_offset_zyx=(7.0, 8.0, 9.0),
        physical_units="um",
        registration_status="likely_valid",
    )

    restored = CoordinateTransform.from_metadata(transform.to_metadata())

    assert restored == transform


def test_invalid_permutation_and_spacing_are_rejected() -> None:
    with pytest.raises(ValueError, match="permutation"):
        CoordinateTransform(
            transform_id="bad-permutation",
            axis_permutation=(0, 0, 2),
        )
    with pytest.raises(ValueError, match="positive and finite"):
        CoordinateTransform(
            transform_id="bad-spacing",
            voxel_spacing_xyz=(1.0, 0.0, 1.0),
        )
