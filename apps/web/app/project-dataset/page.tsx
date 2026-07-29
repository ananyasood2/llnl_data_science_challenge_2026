"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  WorkflowSidebar,
  buildWorkflowHref,
  type WorkflowStep,
} from "../components/WorkflowSidebar";
import {
  GeometryMetadata,
  formatGeometryBounds,
  formatGeometryDimensions,
  formatStlFormat,
} from "./geometryMetadata";

type DatasetSlotId = "ctTiffStack" | "npyVolume" | "stlCad" | "graphJson";
type IntakeStatus = "idle" | "loading" | "valid" | "invalid";

type ProjectHeaderProps = {
  projectName: string;
  projectId: string;
  createdDate: string;
};

type DatasetFileSlot = {
  id: DatasetSlotId;
  label: string;
  description: string;
  required: boolean;
  accept: string;
  multiple?: boolean;
};

type IntakeDimensions = {
  x?: number;
  y?: number;
  z?: number;
};

type IntakeRange = {
  min: number;
  max: number;
};

type IntakeResult = {
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

type SlotState = {
  status: IntakeStatus;
  files: string[];
  result?: IntakeResult;
  error?: string;
};

type DatasetUploadPanelProps = {
  files: DatasetFileSlot[];
  slotStates: Record<DatasetSlotId, SlotState>;
  onFileChange: (slotId: DatasetSlotId, files: FileList | null) => void;
};

type VoxelSizeInputProps = {
  valueMicron: string;
  unit: "micron";
  detectedValueMicron?: number;
  source: "manual" | "detected" | "missing";
  onChange: (value: string) => void;
};

type SampleLookupProps = {
  strutDesign: string;
  targetRelativeDensityPercent: string;
  intentionalDefectCondition: "0%" | "0.5%" | "1%";
  strutDesignOptions: string[];
  relativeDensityOptions: string[];
  onStrutDesignChange: (value: string) => void;
  onTargetRelativeDensityChange: (value: string) => void;
  onIntentionalDefectConditionChange: (value: "0%" | "0.5%" | "1%") => void;
};

type ValidationChecklistProps = {
  items: {
    label: string;
    optional?: boolean;
    passed: boolean;
    pending?: boolean;
  }[];
};

type StartAnalysisButtonProps = {
  disabled: boolean;
  loading: boolean;
  onClick: () => void;
  error?: string | null;
};

const datasetFiles: DatasetFileSlot[] = [
  {
    id: "ctTiffStack",
    label: "CT TIFF stack",
    description: "Required source image stack for inspection.",
    required: true,
    accept: ".tif,.tiff",
    multiple: true,
  },
  {
    id: "npyVolume",
    label: ".npy override",
    description: "Advanced optional override; must match CT stack dimensions.",
    required: false,
    accept: ".npy",
  },
  {
    id: "stlCad",
    label: "STL / CAD",
    description: "Optional design reference geometry.",
    required: false,
    accept: ".stl,.step,.stp",
  },
  {
    id: "graphJson",
    label: "Graph / JSON",
    description: "Optional lattice graph or node-edge metadata.",
    required: false,
    accept: ".json,.graphml",
  },
];

const initialSlotStates: Record<DatasetSlotId, SlotState> = {
  ctTiffStack: { status: "idle", files: [] },
  npyVolume: { status: "idle", files: [] },
  stlCad: { status: "idle", files: [] },
  graphJson: { status: "idle", files: [] },
};

const sampleDesignOptions = ["350 micron strut"];
const relativeDensityOptions = ["10"];
const defectConditionOptions = ["0%", "0.5%", "1%"] as const;

function getAnalysisApiUrl() {
  return process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://localhost:8000";
}

function formatDimensions(dimensions: IntakeDimensions) {
  return [dimensions.x, dimensions.y, dimensions.z]
    .filter((value): value is number => typeof value === "number")
    .join(" x ");
}

function hasPositiveVoxelSize(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

async function validateDatasetSlot(
  slotId: DatasetSlotId,
  files: File[],
  expectedDimensions?: IntakeDimensions,
  datasetId?: string | null,
) {
  const formData = new FormData();

  formData.append("slot", slotId);
  files.forEach((file) => formData.append("files", file));
  if (datasetId) {
    formData.append("dataset_id", datasetId);
  }
  if (expectedDimensions?.x) {
    formData.append("expected_x", String(expectedDimensions.x));
  }
  if (expectedDimensions?.y) {
    formData.append("expected_y", String(expectedDimensions.y));
  }
  if (expectedDimensions?.z) {
    formData.append("expected_z", String(expectedDimensions.z));
  }

  const response = await fetch(`${getAnalysisApiUrl()}/v1/datasets/intake`, {
    method: "POST",
    body: formData,
  });

  let payload: unknown = null;

  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : `Dataset intake failed with HTTP ${response.status}.`;
    throw new Error(detail);
  }

  return payload as IntakeResult;
}

function ProjectHeader({ projectName, projectId, createdDate }: ProjectHeaderProps) {
  return (
    <section className="dataset-panel project-header" aria-labelledby="project-heading">
      <div>
        <p className="panel-kicker">Inspection project</p>
        <h2 id="project-heading">{projectName}</h2>
      </div>
      <div className="project-actions" aria-label="Project actions">
        <button type="button">Create project</button>
        <button type="button">Open project</button>
      </div>
      <dl className="project-meta">
        <div>
          <dt>Project ID</dt>
          <dd>{projectId}</dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{createdDate}</dd>
        </div>
      </dl>
    </section>
  );
}

function DatasetUploadPanel({
  files,
  slotStates,
  onFileChange,
}: DatasetUploadPanelProps) {
  return (
    <section className="dataset-panel" aria-labelledby="dataset-upload-heading">
      <div className="section-heading">
        <p className="panel-kicker">Dataset intake</p>
        <h2 id="dataset-upload-heading">Dataset files</h2>
      </div>
      <div className="upload-grid">
        {files.map((file) => {
          const state = slotStates[file.id];
          const hasErrors = state.status === "invalid";

          return (
            <label
              className={hasErrors ? "upload-field upload-field-error" : "upload-field"}
              key={file.id}
            >
              <span className="upload-copy">
                <span className="upload-title">
                  {file.label}
                  <span className={file.required ? "required-tag" : "optional-tag"}>
                    {file.required ? "Required" : "Optional"}
                  </span>
                  <span className={`slot-status slot-${state.status}`}>
                    {state.status}
                  </span>
                </span>
                <span>{file.description}</span>
              </span>
              <input
                type="file"
                accept={file.accept}
                multiple={file.multiple}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  onFileChange(file.id, event.target.files)
                }
              />
              {state.files.length > 0 ? (
                <span className="file-summary">{state.files.join(", ")}</span>
              ) : null}
              {state.result?.generated_file_names?.length ? (
                <span className="file-summary">
                  Generated: {state.result.generated_file_names.join(", ")}
                </span>
              ) : null}
              {state.result?.dimensions ? (
                <span className="file-summary">
                  Dimensions: {formatDimensions(state.result.dimensions)}
                </span>
              ) : null}
              {state.result?.intensity_range ? (
                <span className="file-summary">
                  Intensity: {state.result.intensity_range.min} to{" "}
                  {state.result.intensity_range.max}
                </span>
              ) : null}
              {state.result?.geometry_metadata ? (
                <>
                  <span className="file-summary">
                    Geometry: {formatStlFormat(state.result.geometry_metadata.format)},{" "}
                    {state.result.geometry_metadata.triangle_count} triangles,{" "}
                    {state.result.geometry_metadata.vertex_count} vertices
                  </span>
                  <span className="file-summary">
                    Bounds: {formatGeometryBounds(state.result.geometry_metadata)}
                  </span>
                  <span className="file-summary">
                    Bounding box: {formatGeometryDimensions(state.result.geometry_metadata)}
                  </span>
                </>
              ) : null}
              {state.result?.warnings?.map((warning) => (
                <span className="inline-warning" key={warning}>
                  {warning}
                </span>
              ))}
              {state.error ? <span className="inline-error">{state.error}</span> : null}
              {state.result?.errors?.map((error) => (
                <span className="inline-error" key={error}>
                  {error}
                </span>
              ))}
            </label>
          );
        })}
      </div>
    </section>
  );
}

function VoxelSizeInput({
  valueMicron,
  unit,
  detectedValueMicron,
  source,
  onChange,
}: VoxelSizeInputProps) {
  const isOverride =
    source === "manual" &&
    typeof detectedValueMicron === "number" &&
    valueMicron !== String(detectedValueMicron);

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="voxel-heading">
      <div className="section-heading">
        <p className="panel-kicker">Scale</p>
        <h2 id="voxel-heading">
          Voxel size
          {source === "detected" ? <span className="detected-tag">Detected</span> : null}
          {isOverride ? <span className="override-tag">Override</span> : null}
        </h2>
      </div>
      <label className="numeric-field">
        <span>Voxel edge length</span>
        <span className="input-with-unit">
          <input
            type="number"
            min="0"
            step="0.01"
            value={valueMicron}
            onChange={(event) => onChange(event.target.value)}
          />
          <span>{unit}</span>
        </span>
      </label>
      {source === "missing" ? (
        <p className="field-note">
          Optional. Leave blank to keep downstream distances and measurements in
          pixels/voxels.
        </p>
      ) : null}
      {isOverride ? (
        <p className="field-note">
          Detected value was {detectedValueMicron} micron. The manual value will be
          used for downstream analysis.
        </p>
      ) : null}
    </section>
  );
}

function SampleLookup({
  strutDesign,
  targetRelativeDensityPercent,
  intentionalDefectCondition,
  strutDesignOptions,
  relativeDensityOptions,
  onStrutDesignChange,
  onTargetRelativeDensityChange,
  onIntentionalDefectConditionChange,
}: SampleLookupProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="sample-heading">
      <div className="section-heading">
        <p className="panel-kicker">Sample lookup</p>
        <h2 id="sample-heading">Design context</h2>
      </div>
      <div className="lookup-grid">
        <label>
          <span>Strut design</span>
          <input
            type="search"
            list="strut-design-options"
            value={strutDesign}
            onChange={(event) => onStrutDesignChange(event.target.value)}
          />
          <datalist id="strut-design-options">
            {strutDesignOptions.map((option) => (
              <option value={option} key={option} />
            ))}
          </datalist>
        </label>
        <label>
          <span>Target relative density</span>
          <span className="input-with-unit">
            <input
              type="number"
              list="relative-density-options"
              min="0"
              max="100"
              step="0.1"
              value={targetRelativeDensityPercent}
              onChange={(event) => onTargetRelativeDensityChange(event.target.value)}
            />
            <span>%</span>
          </span>
          <datalist id="relative-density-options">
            {relativeDensityOptions.map((option) => (
              <option value={option} key={option} />
            ))}
          </datalist>
        </label>
        <label>
          <span>Intentional defect condition</span>
          <select
            value={intentionalDefectCondition}
            onChange={(event) =>
              onIntentionalDefectConditionChange(
                event.target.value as SampleLookupProps["intentionalDefectCondition"],
              )
            }
          >
            {defectConditionOptions.map((option) => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  );
}

function ValidationChecklist({ items }: ValidationChecklistProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="validation-heading">
      <div className="section-heading">
        <p className="panel-kicker">Readiness</p>
        <h2 id="validation-heading">Validation checklist</h2>
      </div>
      <ul className="checklist">
        {items.map((item) => (
          <li key={item.label}>
            <span
              className={item.passed ? "check-indicator passed" : "check-indicator"}
              aria-hidden="true"
            />
            <span>{item.label}</span>
            {item.pending ? <span className="slot-status slot-loading">loading</span> : null}
            {item.optional ? <span className="optional-tag">Optional</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function StartAnalysisButton({
  disabled,
  loading,
  onClick,
  error,
}: StartAnalysisButtonProps) {
  return (
    <section className="start-panel" aria-label="Start analysis">
      <div>
        <p className="panel-kicker">Pipeline</p>
        <h2>Ready for segmentation</h2>
        {error ? <p className="inline-error">{error}</p> : null}
      </div>
      <button type="button" disabled={disabled} onClick={onClick}>
        {loading ? "Running analysis" : "Start analysis"}
      </button>
    </section>
  );
}

export default function ProjectDatasetPage() {
  const router = useRouter();
  const [slotStates, setSlotStates] = useState(initialSlotStates);
  const [voxelSizeMicron, setVoxelSizeMicron] = useState("");
  const [voxelSizeSource, setVoxelSizeSource] =
    useState<VoxelSizeInputProps["source"]>("missing");
  const [strutDesign, setStrutDesign] = useState(sampleDesignOptions[0]);
  const [targetRelativeDensityPercent, setTargetRelativeDensityPercent] =
    useState(relativeDensityOptions[0]);
  const [intentionalDefectCondition, setIntentionalDefectCondition] =
    useState<SampleLookupProps["intentionalDefectCondition"]>("0%");
  const [analysisStart, setAnalysisStart] = useState<{
    loading: boolean;
    error: string | null;
  }>({ loading: false, error: null });

  const anyLoading = Object.values(slotStates).some(
    (slotState) => slotState.status === "loading",
  );
  const ctLoaded = slotStates.ctTiffStack.status === "valid";
  const normalizedVolumeReady =
    ctLoaded ||
    slotStates.npyVolume.status === "valid";
  const stlLoaded = slotStates.stlCad.status === "valid";
  const graphLoaded = slotStates.graphJson.status === "valid";
  const dimensionsDetected = [slotStates.ctTiffStack, slotStates.npyVolume].some(
    (slotState) => Boolean(slotState.result?.dimensions),
  );
  const detectedVoxelSizeCandidate = Object.values(slotStates).find(
    (slotState) => typeof slotState.result?.voxel_size_micron === "number",
  )?.result?.voxel_size_micron;
  const detectedVoxelSize =
    typeof detectedVoxelSizeCandidate === "number"
      ? detectedVoxelSizeCandidate
      : undefined;
  const voxelSizeKnown =
    hasPositiveVoxelSize(voxelSizeMicron) || typeof detectedVoxelSize === "number";
  const voxelSizeUnavailable = useMemo(
    () =>
      [slotStates.ctTiffStack, slotStates.npyVolume].some((slotState) =>
        slotState.result?.warnings?.some((warning) =>
          warning.toLowerCase().includes("voxel size"),
        ),
      ) && !voxelSizeKnown,
    [slotStates, voxelSizeKnown],
  );

  useEffect(() => {
    if (typeof detectedVoxelSize !== "number") {
      if (!hasPositiveVoxelSize(voxelSizeMicron)) {
        setVoxelSizeSource("missing");
      }
      return;
    }

    if (voxelSizeSource !== "manual" || voxelSizeMicron === "") {
      setVoxelSizeMicron(String(detectedVoxelSize));
      setVoxelSizeSource("detected");
    }
  }, [detectedVoxelSize, voxelSizeMicron, voxelSizeSource]);

  const checklistItems = [
    { label: "CT loaded", passed: ctLoaded },
    { label: "Normalized NPY volume ready", passed: normalizedVolumeReady },
    {
      label: voxelSizeKnown
        ? "Micron voxel size verified"
        : "Scale unknown; measurements use pixels/voxels",
      optional: !voxelSizeKnown,
      passed: true,
    },
    {
      label: "Dimensions detected",
      passed: dimensionsDetected,
      pending: anyLoading,
    },
    { label: "STL loaded", optional: true, passed: stlLoaded },
    { label: "Graph loaded", optional: true, passed: graphLoaded },
  ];

  const requiredItemsPassed = checklistItems
    .filter((item) => !item.optional)
    .every((item) => item.passed);
  const activeDatasetId =
    slotStates.ctTiffStack.result?.dataset_id ??
    slotStates.npyVolume.result?.dataset_id ??
    null;
  const activeDimensions =
    slotStates.ctTiffStack.result?.dimensions ??
    slotStates.npyVolume.result?.dimensions;
  const activeDatasetName =
    slotStates.ctTiffStack.files[0] ??
    slotStates.npyVolume.files[0] ??
    "validated dataset";
  const downstreamParams =
    activeDatasetId && activeDimensions && requiredItemsPassed && !anyLoading
      ? new URLSearchParams({
          dataset: activeDatasetName,
          projectId: "Pending",
          datasetId: activeDatasetId,
          scaleUnit: voxelSizeKnown ? "micron" : "voxel",
          x: String(activeDimensions.x ?? "unknown"),
          y: String(activeDimensions.y ?? "unknown"),
          z: String(activeDimensions.z ?? "unknown"),
        })
      : null;

  if (
    downstreamParams &&
    voxelSizeKnown &&
    hasPositiveVoxelSize(voxelSizeMicron)
  ) {
    downstreamParams.set("voxelSizeMicron", voxelSizeMicron);
  } else if (
    downstreamParams &&
    voxelSizeKnown &&
    typeof detectedVoxelSize === "number"
  ) {
    downstreamParams.set("voxelSizeMicron", String(detectedVoxelSize));
  }

  const downstreamHref = downstreamParams
    ? buildWorkflowHref("/segmentation", downstreamParams)
    : null;
  const workflowSteps: WorkflowStep[] = [
    {
      id: "project-dataset",
      href: buildWorkflowHref("/project-dataset"),
      state: "active",
    },
    {
      id: "segmentation",
      href: downstreamHref,
      state: downstreamHref ? "available" : "locked",
    },
    {
      id: "structure-analysis",
      href: null,
      state: "locked",
    },
  ];

  async function handleFileChange(slotId: DatasetSlotId, fileList: FileList | null) {
    const selectedFiles = Array.from(fileList ?? []);

    if (selectedFiles.length === 0) {
      setSlotStates((current) => ({
        ...current,
        [slotId]: initialSlotStates[slotId],
      }));
      return;
    }

    const expectedDimensions = slotStates.ctTiffStack.result?.dimensions;
    const tiffDatasetId = slotStates.ctTiffStack.result?.dataset_id;

    if (slotId === "npyVolume" && !expectedDimensions) {
      setSlotStates((current) => ({
        ...current,
        [slotId]: {
          status: "invalid",
          files: selectedFiles.map((file) => file.name),
          error: "Upload and validate the CT TIFF stack before adding a .npy override.",
        },
      }));
      return;
    }

    setSlotStates((current) => ({
      ...current,
      [slotId]: {
        status: "loading",
        files: selectedFiles.map((file) => file.name),
      },
    }));

    try {
      const result = await validateDatasetSlot(
        slotId,
        selectedFiles,
        slotId === "npyVolume" ? expectedDimensions : undefined,
        slotId === "npyVolume" || slotId === "stlCad" ? tiffDatasetId : undefined,
      );

      setSlotStates((current) => ({
        ...current,
        [slotId]: {
          status: result.valid ? "valid" : "invalid",
          files: selectedFiles.map((file) => file.name),
          result,
          error: result.valid
            ? undefined
            : "Data intake rejected this file. Review the validation details.",
        },
      }));
    } catch (error) {
      setSlotStates((current) => ({
        ...current,
        [slotId]: {
          status: "invalid",
          files: selectedFiles.map((file) => file.name),
          error:
            error instanceof Error
              ? error.message
              : "Dataset intake failed for this upload slot.",
        },
      }));
    }
  }

  function handleVoxelSizeChange(value: string) {
    setVoxelSizeMicron(value);

    if (!hasPositiveVoxelSize(value)) {
      setVoxelSizeSource("missing");
      return;
    }

    setVoxelSizeSource(
      typeof detectedVoxelSize === "number" && value === String(detectedVoxelSize)
        ? "detected"
        : "manual",
    );
  }

  async function handleStartAnalysis() {
    const dimensions = slotStates.ctTiffStack.result?.dimensions;
    const datasetName =
      slotStates.ctTiffStack.files[0] ?? slotStates.npyVolume.files[0] ?? "validated dataset";
    const datasetId =
      slotStates.ctTiffStack.result?.dataset_id ??
      slotStates.npyVolume.result?.dataset_id;

    if (!datasetId) {
      setAnalysisStart({
        loading: false,
        error: "Dataset has not been persisted yet.",
      });
      return;
    }

    setAnalysisStart({ loading: true, error: null });

    let jobPayload: {
      job_id: string;
      project_id: string;
      status: string;
    };

    try {
      const response = await fetch(
        `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(
          datasetId,
        )}/analysis-jobs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            project_id: null,
            dataset_name: datasetName,
            voxel_size_micron: voxelSizeKnown
              ? Number(
                  hasPositiveVoxelSize(voxelSizeMicron)
                    ? voxelSizeMicron
                    : detectedVoxelSize,
                )
              : null,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`Analysis job failed with HTTP ${response.status}.`);
      }

      jobPayload = (await response.json()) as typeof jobPayload;
      if (jobPayload.status === "failed") {
        throw new Error("Analysis job failed. Open segmentation for details.");
      }
    } catch (error) {
      setAnalysisStart({
        loading: false,
        error:
          error instanceof Error
            ? error.message
            : "Unable to start the analysis job.",
      });
      return;
    }

    const params = new URLSearchParams({
      projectId: jobPayload.project_id,
      dataset: datasetName,
      scaleUnit: voxelSizeKnown ? "micron" : "voxel",
      datasetId,
      jobId: jobPayload.job_id,
    });

    if (voxelSizeKnown) {
      params.set(
        "voxelSizeMicron",
        hasPositiveVoxelSize(voxelSizeMicron)
          ? voxelSizeMicron
          : String(detectedVoxelSize),
      );
    }

    if (dimensions?.x) {
      params.set("x", String(dimensions.x));
    }
    if (dimensions?.y) {
      params.set("y", String(dimensions.y));
    }
    if (dimensions?.z) {
      params.set("z", String(dimensions.z));
    }

    router.push(`/segmentation?${params.toString()}`);
  }

  return (
    <main className="workspace">
      <WorkflowSidebar steps={workflowSteps} />

      <section className="content dataset-content">
        <div className="eyebrow">What am I analyzing?</div>
        <h1>Project and dataset intake</h1>
        <p className="lede">
          Create or open an inspection project, attach the required CT inputs, and
          confirm sample metadata before starting downstream analysis.
        </p>

        {voxelSizeUnavailable ? (
          <div className="warning-banner" role="alert">
            Voxel size was not detected from the uploaded dataset. You can continue;
            downstream distances and measurements will be labeled in pixels or voxels
            until a verified micron value is entered.
          </div>
        ) : null}

        <div className="dataset-layout">
          <ProjectHeader
            projectName="Untitled inspection"
            projectId="Pending"
            createdDate="Not created"
          />
          <DatasetUploadPanel
            files={datasetFiles}
            slotStates={slotStates}
            onFileChange={handleFileChange}
          />
          <div className="dataset-two-column">
            <VoxelSizeInput
              valueMicron={voxelSizeMicron}
              unit="micron"
              detectedValueMicron={detectedVoxelSize}
              source={voxelSizeSource}
              onChange={handleVoxelSizeChange}
            />
            <SampleLookup
              strutDesign={strutDesign}
              targetRelativeDensityPercent={targetRelativeDensityPercent}
              intentionalDefectCondition={intentionalDefectCondition}
              strutDesignOptions={sampleDesignOptions}
              relativeDensityOptions={relativeDensityOptions}
              onStrutDesignChange={setStrutDesign}
              onTargetRelativeDensityChange={setTargetRelativeDensityPercent}
              onIntentionalDefectConditionChange={setIntentionalDefectCondition}
            />
          </div>
          <ValidationChecklist items={checklistItems} />
          <StartAnalysisButton
            disabled={!requiredItemsPassed || anyLoading || analysisStart.loading}
            loading={anyLoading || analysisStart.loading}
            error={analysisStart.error}
            onClick={handleStartAnalysis}
          />
        </div>
      </section>
    </main>
  );
}
