import type { DatasetContext } from "./SegmentationClient";

export type Axis = "X" | "Y" | "Z";

export type VolumeCoordinate = {
  x: number;
  y: number;
  z: number;
};

export type VoxelCoordinateInput = {
  x: string;
  y: string;
  z: string;
};

export type VolumeBounds = {
  x: number;
  y: number;
  z: number;
};

function getDimensionLimit(value: string) {
  const parsed = Number(value);

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 255;
  }

  return Math.max(0, Math.floor(parsed) - 1);
}

export function getVolumeBounds(context: DatasetContext): VolumeBounds {
  return {
    x: getDimensionLimit(context.dimensions.x),
    y: getDimensionLimit(context.dimensions.y),
    z: getDimensionLimit(context.dimensions.z),
  };
}

export function getSliceLimit(axis: Axis, context: DatasetContext) {
  const bounds = getVolumeBounds(context);

  if (axis === "X") {
    return bounds.x;
  }

  if (axis === "Y") {
    return bounds.y;
  }

  return bounds.z;
}

export function validateVoxelCoordinateInput(
  values: VoxelCoordinateInput,
  bounds: VolumeBounds,
) {
  const errors: Partial<Record<keyof VoxelCoordinateInput, string>> = {};
  const coordinate = { x: 0, y: 0, z: 0 };
  const axes: (keyof VoxelCoordinateInput)[] = ["x", "y", "z"];

  for (const coordinateAxis of axes) {
    const rawValue = values[coordinateAxis].trim();

    if (!rawValue) {
      errors[coordinateAxis] = "Required.";
      continue;
    }

    if (!/^-?\d+$/.test(rawValue)) {
      errors[coordinateAxis] = "Use an integer voxel index.";
      continue;
    }

    const parsed = Number(rawValue);

    if (parsed < 0 || parsed > bounds[coordinateAxis]) {
      errors[coordinateAxis] = `Expected 0-${bounds[coordinateAxis]} voxels.`;
      continue;
    }

    coordinate[coordinateAxis] = parsed;
  }

  return {
    coordinate,
    errors,
    valid: Object.keys(errors).length === 0,
  };
}

export function getSliceIndexForCoordinate(
  axis: Axis,
  coordinate: VolumeCoordinate,
) {
  if (axis === "X") {
    return coordinate.x;
  }

  if (axis === "Y") {
    return coordinate.y;
  }

  return coordinate.z;
}

export function getMarkerPosition(
  axis: Axis,
  coordinate: VolumeCoordinate,
  bounds: VolumeBounds,
) {
  if (axis === "X") {
    return {
      left: bounds.y === 0 ? 0 : (coordinate.y / bounds.y) * 100,
      top: bounds.z === 0 ? 0 : (coordinate.z / bounds.z) * 100,
    };
  }

  if (axis === "Y") {
    return {
      left: bounds.x === 0 ? 0 : (coordinate.x / bounds.x) * 100,
      top: bounds.z === 0 ? 0 : (coordinate.z / bounds.z) * 100,
    };
  }

  return {
    left: bounds.x === 0 ? 0 : (coordinate.x / bounds.x) * 100,
    top: bounds.y === 0 ? 0 : (coordinate.y / bounds.y) * 100,
  };
}
