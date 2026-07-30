import type { GeometryMetadata } from "./geometryMetadata";

export type DatasetSlotId = "ctTiffStack" | "npyVolume" | "stlCad" | "graphJson";
export type IntakeStatus = "idle" | "loading" | "valid" | "invalid";

export type IntakeDimensions = {
  x?: number;
  y?: number;
  z?: number;
};

export type IntakeRange = {
  min: number;
  max: number;
};

export type IntakeResult = {
  valid: boolean;
  dataset_id?: string | null;
  slot?: DatasetSlotId;
  file_names?: string[];
  generated_file_names?: string[];
  fileType?: string;
  dimensions?: IntakeDimensions;
  intensity_range?: IntakeRange;
  geometry_metadata?: GeometryMetadata | null;
  embedded_metadata?: Record<string, unknown> | null;
  voxel_size_micron?: number | null;
  warnings?: string[];
  errors?: string[];
  demo_mode?: boolean;
};

export type SlotState = {
  status: IntakeStatus;
  files: string[];
  result?: IntakeResult;
  error?: string;
};

export const initialSlotStates: Record<DatasetSlotId, SlotState> = {
  ctTiffStack: { status: "idle", files: [] },
  npyVolume: { status: "idle", files: [] },
  stlCad: { status: "idle", files: [] },
  graphJson: { status: "idle", files: [] },
};

export function namesFromFiles(files: Pick<File, "name">[]) {
  return files.map((file) => file.name);
}

export function slotLoadingState(files: Pick<File, "name">[]): SlotState {
  return {
    status: "loading",
    files: namesFromFiles(files),
  };
}

export function slotSuccessState(
  files: Pick<File, "name">[],
  result: IntakeResult,
): SlotState {
  return {
    status: result.valid ? "valid" : "invalid",
    files: namesFromFiles(files),
    result,
    error: result.valid
      ? undefined
      : "Data intake rejected this file. Review the validation details.",
  };
}

export function slotFailureState(
  files: Pick<File, "name">[],
  error: unknown,
): SlotState {
  return {
    status: "invalid",
    files: namesFromFiles(files),
    error:
      error instanceof Error
        ? error.message
        : "Dataset intake failed for this upload slot.",
  };
}
