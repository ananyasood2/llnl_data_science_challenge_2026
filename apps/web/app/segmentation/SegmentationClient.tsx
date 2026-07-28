"use client";

/* eslint-disable @next/next/no-img-element */

import { useEffect, useRef, useState, type PointerEvent } from "react";

export type DatasetContext = {
  datasetId: string | null;
  dataset: string;
  projectId: string;
  dimensions: {
    x: string;
    y: string;
    z: string;
  };
  voxelSizeMicron: string;
};

type Axis = "X" | "Y" | "Z";
type ViewMode = "original" | "segmentation" | "skeleton" | "defects";

type SliceViewerProps = {
  axis: Axis;
  sliceIndex: number;
  maxSliceIndex: number;
  viewMode: Exclude<ViewMode, "defects">;
  imageUrl: string | null;
  status: SliceFetchState["status"];
  message: string | null;
  zoomPercent: number;
  panOffset: {
    x: number;
    y: number;
  };
  maskPreviewUrl: string | null;
  maskPreviewLoading: boolean;
  overlayEnabled: boolean;
  overlayOpacity: number;
  onAxisChange: (axis: Axis) => void;
  onSliceIndexChange: (index: number) => void;
  onProbeClick: (coordinate: VolumeCoordinate) => void;
  onProbeHover: (coordinate: VolumeCoordinate) => void;
};

type ViewModeTabsProps = {
  value: Exclude<ViewMode, "defects">;
  onChange: (mode: Exclude<ViewMode, "defects">) => void;
};

type ZoomPanControlsProps = {
  zoomPercent: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onPan: (deltaX: number, deltaY: number) => void;
  onReset: () => void;
};

type SegmentationOverlayToggleProps = {
  enabled: boolean;
  opacity: number;
  onChange: (enabled: boolean) => void;
  onOpacityChange: (opacity: number) => void;
};

type VoxelProbeProps = {
  coordinate: {
    x: number;
    y: number;
    z: number;
  };
  intensity: number | null;
  maskValue: 0 | 1 | null;
};

type IntensityHistogramProps = {
  minIntensity: number;
  maxIntensity: number;
  threshold: number;
};

type ThresholdSliderProps = {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
};

type VoxelCountsProps = {
  foreground: number | null;
  background: number | null;
};

type SaveSegmentationButtonProps = {
  disabled: boolean;
  threshold: number;
  saving: boolean;
  result: SavedSegmentation | null;
  error: string | null;
  continueHref: string | null;
  onSave: () => void;
};

type SliceFetchState = {
  status: "idle" | "loading" | "ready" | "empty" | "error";
  imageUrl: string | null;
  message: string | null;
};

type ThresholdPreviewState = {
  status: "idle" | "loading" | "ready" | "error";
  imageUrl: string | null;
  foreground: number | null;
  background: number | null;
  sliceMinIntensity: number | null;
  sliceMaxIntensity: number | null;
  widthPx: number | null;
  heightPx: number | null;
  message: string | null;
};

type VolumeCoordinate = {
  x: number;
  y: number;
  z: number;
};

type SavedSegmentation = {
  status: string;
  dataset_id: string;
  threshold: number;
  foreground_voxel_count: number;
  background_voxel_count: number;
  mask_path: string;
  slice_preview_path: string;
  demo_mode: boolean;
};

const viewModes: {
  id: Exclude<ViewMode, "defects">;
  label: string;
}[] = [
  { id: "original", label: "Original" },
  { id: "segmentation", label: "Segmentation" },
  { id: "skeleton", label: "Skeleton" },
];

function getAnalysisApiUrl() {
  return process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://localhost:8000";
}

function getSliceLimit(axis: Axis, context: DatasetContext) {
  const rawValue =
    axis === "X"
      ? context.dimensions.x
      : axis === "Y"
        ? context.dimensions.y
        : context.dimensions.z;
  const parsed = Number(rawValue);

  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 255;
  }

  return Math.max(0, Math.floor(parsed) - 1);
}

function getSliceUrl(
  datasetId: string,
  axis: Axis,
  sliceIndex: number,
  viewMode: Exclude<ViewMode, "defects">,
) {
  const params = new URLSearchParams({ view: viewMode });

  return `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(
    datasetId,
  )}/slices/${axis.toLowerCase()}/${sliceIndex}?${params.toString()}`;
}

async function fetchSliceImage(
  datasetId: string,
  axis: Axis,
  sliceIndex: number,
  viewMode: Exclude<ViewMode, "defects">,
  signal: AbortSignal,
) {
  const response = await fetch(getSliceUrl(datasetId, axis, sliceIndex, viewMode), {
    headers: {
      Accept: "image/png, application/json",
    },
    signal,
  });

  if (response.status === 404 || response.status === 409) {
    const label =
      viewMode === "original"
        ? "Original slice data is not available for this dataset."
        : `${viewMode} has not been generated for this dataset.`;

    return { status: "empty" as const, imageUrl: null, message: label };
  }

  if (!response.ok) {
    throw new Error(`Slice fetch failed with HTTP ${response.status}.`);
  }

  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const payload = (await response.json()) as {
      image_uri?: string | null;
    };

    if (!payload.image_uri) {
      return {
        status: "empty" as const,
        imageUrl: null,
        message: "Slice response did not include an image URI.",
      };
    }

    return { status: "ready" as const, imageUrl: payload.image_uri, message: null };
  }

  const blob = await response.blob();

  return {
    status: "ready" as const,
    imageUrl: URL.createObjectURL(blob),
    message: null,
  };
}

async function fetchThresholdPreview(
  datasetId: string,
  axis: Axis,
  sliceIndex: number,
  threshold: number,
  signal: AbortSignal,
) {
  const response = await fetch(
    `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(
      datasetId,
    )}/threshold-preview`,
    {
      method: "POST",
      headers: {
        Accept: "image/png",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        threshold,
        axis: axis.toLowerCase(),
        index: sliceIndex,
      }),
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Threshold preview failed with HTTP ${response.status}.`);
  }

  const blob = await response.blob();

  return {
    imageUrl: URL.createObjectURL(blob),
    foreground: Number(response.headers.get("x-foreground-voxel-count")),
    background: Number(response.headers.get("x-background-voxel-count")),
    sliceMinIntensity: Number(response.headers.get("x-slice-min-intensity")),
    sliceMaxIntensity: Number(response.headers.get("x-slice-max-intensity")),
    widthPx: Number(response.headers.get("x-slice-width-px")),
    heightPx: Number(response.headers.get("x-slice-height-px")),
  };
}

async function fetchVoxelProbe(
  datasetId: string,
  coordinate: VolumeCoordinate,
  threshold: number,
  signal: AbortSignal,
) {
  const response = await fetch(
    `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(datasetId)}/voxel-probe`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ...coordinate, threshold }),
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Voxel probe failed with HTTP ${response.status}.`);
  }

  return (await response.json()) as VolumeCoordinate & {
    intensity: number;
    mask_value: 0 | 1;
  };
}

async function saveSegmentation(datasetId: string, threshold: number) {
  const response = await fetch(
    `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(datasetId)}/segmentation`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ threshold }),
    },
  );

  if (!response.ok) {
    throw new Error(`Segmentation save failed with HTTP ${response.status}.`);
  }

  return (await response.json()) as SavedSegmentation;
}

function formatVoxelCount(value: number | null) {
  return typeof value === "number" ? value.toLocaleString() : "Pending";
}

function ViewModeTabs({ value, onChange }: ViewModeTabsProps) {
  return (
    <div className="view-tabs" role="tablist" aria-label="Slice view mode">
      {viewModes.map((mode) => (
        <button
          type="button"
          role="tab"
          aria-selected={value === mode.id}
          className={value === mode.id ? "view-tab active" : "view-tab"}
          key={mode.id}
          onClick={() => onChange(mode.id)}
        >
          {mode.label}
        </button>
      ))}
      <span
        className="view-tab disabled"
        role="tab"
        aria-disabled="true"
        title="Available after defect detection"
      >
        Defects
        <span>Available after defect detection</span>
      </span>
    </div>
  );
}

function SliceViewer({
  axis,
  sliceIndex,
  maxSliceIndex,
  viewMode,
  imageUrl,
  status,
  message,
  zoomPercent,
  panOffset,
  maskPreviewUrl,
  maskPreviewLoading,
  overlayEnabled,
  overlayOpacity,
  onAxisChange,
  onSliceIndexChange,
  onProbeClick,
  onProbeHover,
}: SliceViewerProps) {
  function coordinateFromPointerEvent(event: PointerEvent<HTMLImageElement>) {
    const image = event.currentTarget;
    const rect = image.getBoundingClientRect();
    const normalizedX = (event.clientX - rect.left) / rect.width;
    const normalizedY = (event.clientY - rect.top) / rect.height;

    if (normalizedX < 0 || normalizedX > 1 || normalizedY < 0 || normalizedY > 1) {
      return null;
    }

    const column = Math.max(
      0,
      Math.min(image.naturalWidth - 1, Math.floor(normalizedX * image.naturalWidth)),
    );
    const row = Math.max(
      0,
      Math.min(image.naturalHeight - 1, Math.floor(normalizedY * image.naturalHeight)),
    );

    if (axis === "X") {
      return { x: sliceIndex, y: column, z: row };
    }

    if (axis === "Y") {
      return { x: column, y: sliceIndex, z: row };
    }

    return { x: column, y: row, z: sliceIndex };
  }

  function handlePointerMove(event: PointerEvent<HTMLImageElement>) {
    const coordinate = coordinateFromPointerEvent(event);

    if (coordinate) {
      onProbeHover(coordinate);
    }
  }

  function handleClick(event: PointerEvent<HTMLImageElement>) {
    const coordinate = coordinateFromPointerEvent(event);

    if (coordinate) {
      onProbeClick(coordinate);
    }
  }

  return (
    <section className="dataset-panel slice-viewer" aria-labelledby="slice-viewer-heading">
      <div className="slice-toolbar">
        <div className="section-heading">
          <p className="panel-kicker">Slice viewer</p>
          <h2 id="slice-viewer-heading">{viewMode} view</h2>
        </div>
        <label className="axis-control">
          <span>Axis</span>
          <select
            value={axis}
            onChange={(event) => onAxisChange(event.target.value as Axis)}
          >
            <option value="X">X</option>
            <option value="Y">Y</option>
            <option value="Z">Z</option>
          </select>
        </label>
      </div>

      <div className="slice-canvas">
        {status === "ready" && imageUrl ? (
          <>
            <img
              className="slice-image"
              src={imageUrl}
              alt={`${viewMode} slice ${sliceIndex} on ${axis} axis`}
              onClick={handleClick}
              onPointerMove={handlePointerMove}
              style={{
                transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${
                  zoomPercent / 100
                })`,
              }}
            />
            {overlayEnabled && maskPreviewUrl && viewMode === "original" ? (
              <img
                className="mask-preview-image"
                src={maskPreviewUrl}
                alt="Threshold mask preview"
                aria-hidden="true"
                style={{
                  opacity: overlayOpacity,
                  transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${
                    zoomPercent / 100
                  })`,
                }}
              />
            ) : null}
            {maskPreviewLoading ? (
              <span className="mask-loading" role="status">
                Updating mask
              </span>
            ) : null}
          </>
        ) : (
          <div className={`slice-state slice-state-${status}`} role="status">
            <strong>
              {status === "loading"
                ? "Loading slice"
                : status === "error"
                  ? "Slice unavailable"
                  : status === "empty"
                    ? "No slice image"
                    : "Waiting for dataset"}
            </strong>
            <span>{message}</span>
          </div>
        )}
      </div>

      <label className="slice-slider">
        <span>
          Slice index <strong>{sliceIndex}</strong>
        </span>
        <input
          type="range"
          min="0"
          max={maxSliceIndex}
          value={sliceIndex}
          onChange={(event) => onSliceIndexChange(Number(event.target.value))}
        />
      </label>
    </section>
  );
}

function ZoomPanControls({
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onPan,
  onReset,
}: ZoomPanControlsProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="zoom-heading">
      <div className="section-heading">
        <p className="panel-kicker">Navigation</p>
        <h2 id="zoom-heading">Zoom / pan</h2>
      </div>
      <div className="tool-button-row" aria-label="Zoom and pan controls">
        <button type="button" onClick={onZoomOut}>-</button>
        <button type="button">{zoomPercent}%</button>
        <button type="button" onClick={onZoomIn}>+</button>
        <button type="button" onClick={() => onPan(0, -24)}>Up</button>
        <button type="button" onClick={() => onPan(-24, 0)}>Left</button>
        <button type="button" onClick={() => onPan(24, 0)}>Right</button>
        <button type="button" onClick={() => onPan(0, 24)}>Down</button>
        <button type="button" onClick={onReset}>Reset</button>
      </div>
    </section>
  );
}

function SegmentationOverlayToggle({
  enabled,
  opacity,
  onChange,
  onOpacityChange,
}: SegmentationOverlayToggleProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="overlay-heading">
      <div className="section-heading">
        <p className="panel-kicker">Overlay</p>
        <h2 id="overlay-heading">Segmentation mask</h2>
      </div>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>Show mask over original slice</span>
      </label>
      <label className="threshold-control">
        <span>
          Opacity <strong>{Math.round(opacity * 100)}%</strong>
        </span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={opacity}
          onChange={(event) => onOpacityChange(Number(event.target.value))}
        />
      </label>
    </section>
  );
}

function VoxelProbe({ coordinate, intensity, maskValue }: VoxelProbeProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="probe-heading">
      <div className="section-heading">
        <p className="panel-kicker">Probe</p>
        <h2 id="probe-heading">Hovered voxel</h2>
      </div>
      <dl className="metric-list">
        <div>
          <dt>Coordinate</dt>
          <dd>
            {coordinate.x}, {coordinate.y}, {coordinate.z}
          </dd>
        </div>
        <div>
          <dt>Intensity</dt>
          <dd>{intensity ?? "Pending"}</dd>
        </div>
        <div>
          <dt>Mask value</dt>
          <dd>{maskValue ?? "Pending"}</dd>
        </div>
      </dl>
    </section>
  );
}

function IntensityHistogram({
  minIntensity,
  maxIntensity,
  threshold,
}: IntensityHistogramProps) {
  const thresholdPosition =
    maxIntensity === minIntensity
      ? 0
      : ((threshold - minIntensity) / (maxIntensity - minIntensity)) * 100;

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="histogram-heading">
      <div className="section-heading">
        <p className="panel-kicker">Intensity</p>
        <h2 id="histogram-heading">Histogram</h2>
      </div>
      <div className="histogram" aria-label="Intensity histogram preview">
        <span style={{ left: `${thresholdPosition}%` }} />
      </div>
      <div className="histogram-labels">
        <span>{minIntensity}</span>
        <strong>{threshold.toFixed(4)}</strong>
        <span>{maxIntensity}</span>
      </div>
    </section>
  );
}

function ThresholdSlider({
  value,
  min,
  max,
  step,
  onChange,
}: ThresholdSliderProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="threshold-heading">
      <div className="section-heading">
        <p className="panel-kicker">Preview threshold</p>
        <h2 id="threshold-heading">Client mask preview</h2>
      </div>
      <label className="threshold-control">
        <span>
          Threshold <strong>{value.toFixed(4)}</strong>
        </span>
        {/* This slider is for a fast client-facing preview only: mask = volume > threshold.
            It is distinct from the full Segmentation Agent batch job, which persists the
            final mask, slice visualization, voxel counts, reproducible script, and report. */}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </label>
    </section>
  );
}

function VoxelCounts({ foreground, background }: VoxelCountsProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="counts-heading">
      <div className="section-heading">
        <p className="panel-kicker">Live counts</p>
        <h2 id="counts-heading">Voxel counts</h2>
      </div>
      <dl className="metric-list metric-grid">
        <div>
          <dt>Foreground</dt>
          <dd>{formatVoxelCount(foreground)}</dd>
        </div>
        <div>
          <dt>Background</dt>
          <dd>{formatVoxelCount(background)}</dd>
        </div>
      </dl>
    </section>
  );
}

function SaveSegmentationButton({
  disabled,
  threshold,
  saving,
  result,
  error,
  continueHref,
  onSave,
}: SaveSegmentationButtonProps) {
  return (
    <section className="start-panel" aria-label="Save segmentation">
      <div>
        <p className="panel-kicker">Segmentation result</p>
        <h2>Save final mask at threshold {threshold.toFixed(4)}</h2>
        <p className="field-note">
          Persists the chosen threshold, mask, slice visualization, voxel counts, and
          summary for this dataset.
        </p>
        {result ? (
          <p className="inline-success">
            Segmentation saved. Foreground {formatVoxelCount(result.foreground_voxel_count)};
            background {formatVoxelCount(result.background_voxel_count)}.
          </p>
        ) : null}
        {error ? <p className="inline-error">{error}</p> : null}
      </div>
      <div className="save-actions">
        <button type="button" disabled={disabled || saving} onClick={onSave}>
          {saving ? "Saving segmentation" : "Save segmentation"}
        </button>
        {continueHref ? (
          <a className="primary-link" href={continueHref}>
            Continue to skeletonization
          </a>
        ) : null}
      </div>
    </section>
  );
}

export function SegmentationClient({
  datasetContext,
}: {
  datasetContext: DatasetContext;
}) {
  const [axis, setAxis] = useState<Axis>("Z");
  const [sliceIndex, setSliceIndex] = useState(128);
  const [viewMode, setViewMode] = useState<Exclude<ViewMode, "defects">>("original");
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [overlayOpacity, setOverlayOpacity] = useState(0.42);
  const [threshold, setThreshold] = useState(0.005);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [sliceFetch, setSliceFetch] = useState<SliceFetchState>({
    status: "idle",
    imageUrl: null,
    message:
      "Dataset intake does not yet return a stable dataset ID for slice retrieval.",
  });
  const [thresholdPreview, setThresholdPreview] = useState<ThresholdPreviewState>({
    status: "idle",
    imageUrl: null,
    foreground: null,
    background: null,
    sliceMinIntensity: null,
    sliceMaxIntensity: null,
    widthPx: null,
    heightPx: null,
    message: null,
  });
  const [probe, setProbe] = useState<VoxelProbeProps>({
    coordinate: { x: 0, y: 0, z: 0 },
    intensity: null,
    maskValue: null,
  });
  const [segmentationSave, setSegmentationSave] = useState<{
    saving: boolean;
    result: SavedSegmentation | null;
    error: string | null;
  }>({
    saving: false,
    result: null,
    error: null,
  });
  const lastHoverProbeAt = useRef(0);
  const pendingHoverTimeout = useRef<number | null>(null);
  const latestHoverCoordinate = useRef<VolumeCoordinate | null>(null);
  const latestProbeRequestId = useRef(0);
  const probeAbortController = useRef<AbortController | null>(null);
  const maxSliceIndex = getSliceLimit(axis, datasetContext);
  const boundedSliceIndex = Math.min(sliceIndex, maxSliceIndex);
  const preparationStatus = segmentationSave.result
    ? "Segmentation saved"
    : segmentationSave.saving
      ? "Saving segmentation"
      : segmentationSave.error
        ? "Save failed"
        : sliceFetch.status;
  const continueHref =
    datasetContext.datasetId && segmentationSave.result
      ? `/skeletonization?${new URLSearchParams({
          datasetId: datasetContext.datasetId,
          threshold: String(segmentationSave.result.threshold),
          foregroundVoxelCount: String(segmentationSave.result.foreground_voxel_count),
          backgroundVoxelCount: String(segmentationSave.result.background_voxel_count),
        }).toString()}`
      : null;

  useEffect(() => {
    let localObjectUrl: string | null = null;

    if (!datasetContext.datasetId) {
      return;
    }

    const controller = new AbortController();

    // Clear any previous image before starting the external slice request.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSliceFetch({
      status: "loading",
      imageUrl: null,
      message: `Requesting ${viewMode} slice ${boundedSliceIndex} on ${axis} axis.`,
    });

    fetchSliceImage(
      datasetContext.datasetId,
      axis,
      boundedSliceIndex,
      viewMode,
      controller.signal,
    )
      .then((nextState) => {
        if (nextState.imageUrl?.startsWith("blob:")) {
          localObjectUrl = nextState.imageUrl;
        }

        setSliceFetch(nextState);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }

        setSliceFetch({
          status: "error",
          imageUrl: null,
          message:
            error instanceof Error
              ? error.message
              : "Unable to fetch the requested slice image.",
        });
      });

    return () => {
      controller.abort();

      if (localObjectUrl) {
        URL.revokeObjectURL(localObjectUrl);
      }
    };
  }, [axis, boundedSliceIndex, datasetContext.datasetId, viewMode]);

  useEffect(() => {
    let localObjectUrl: string | null = null;

    if (!datasetContext.datasetId) {
      return;
    }

    const datasetId = datasetContext.datasetId;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setThresholdPreview((current) => ({
        ...current,
        status: "loading",
        imageUrl: null,
        message: "Updating threshold preview.",
      }));

      fetchThresholdPreview(
        datasetId,
        axis,
        boundedSliceIndex,
        threshold,
        controller.signal,
      )
        .then((preview) => {
          localObjectUrl = preview.imageUrl;
          setThresholdPreview({
            status: "ready",
            imageUrl: preview.imageUrl,
            foreground: Number.isFinite(preview.foreground) ? preview.foreground : null,
            background: Number.isFinite(preview.background) ? preview.background : null,
            sliceMinIntensity: Number.isFinite(preview.sliceMinIntensity)
              ? preview.sliceMinIntensity
              : null,
            sliceMaxIntensity: Number.isFinite(preview.sliceMaxIntensity)
              ? preview.sliceMaxIntensity
              : null,
            widthPx: Number.isFinite(preview.widthPx) ? preview.widthPx : null,
            heightPx: Number.isFinite(preview.heightPx) ? preview.heightPx : null,
            message: null,
          });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) {
            return;
          }

          setThresholdPreview((current) => ({
            ...current,
            status: "error",
            imageUrl: null,
            message:
              error instanceof Error
                ? error.message
                : "Unable to update threshold preview.",
          }));
        });
    }, 275);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();

      if (localObjectUrl) {
        URL.revokeObjectURL(localObjectUrl);
      }
    };
  }, [axis, boundedSliceIndex, datasetContext.datasetId, threshold]);

  useEffect(() => {
    return () => {
      if (pendingHoverTimeout.current !== null) {
        window.clearTimeout(pendingHoverTimeout.current);
      }

      probeAbortController.current?.abort();
    };
  }, []);

  function runProbe(coordinate: VolumeCoordinate) {
    setProbe((current) => ({ ...current, coordinate }));

    if (!datasetContext.datasetId) {
      return;
    }

    probeAbortController.current?.abort();
    const requestId = latestProbeRequestId.current + 1;
    latestProbeRequestId.current = requestId;
    const controller = new AbortController();
    probeAbortController.current = controller;

    fetchVoxelProbe(datasetContext.datasetId, coordinate, threshold, controller.signal)
      .then((nextProbe) => {
        if (requestId !== latestProbeRequestId.current) {
          return;
        }

        setProbe({
          coordinate: {
            x: nextProbe.x,
            y: nextProbe.y,
            z: nextProbe.z,
          },
          intensity: nextProbe.intensity,
          maskValue: nextProbe.mask_value,
        });
      })
      .catch(() => {
        if (controller.signal.aborted || requestId !== latestProbeRequestId.current) {
          return;
        }

        setProbe({ coordinate, intensity: null, maskValue: null });
      });
  }

  function handleProbeClick(coordinate: VolumeCoordinate) {
    if (pendingHoverTimeout.current !== null) {
      window.clearTimeout(pendingHoverTimeout.current);
      pendingHoverTimeout.current = null;
    }

    lastHoverProbeAt.current = Date.now();
    runProbe(coordinate);
  }

  function handleProbeHover(coordinate: VolumeCoordinate) {
    latestHoverCoordinate.current = coordinate;
    const now = Date.now();
    const elapsedMs = now - lastHoverProbeAt.current;
    const throttleMs = 80;

    if (elapsedMs >= throttleMs) {
      lastHoverProbeAt.current = now;
      runProbe(coordinate);
      return;
    }

    if (pendingHoverTimeout.current !== null) {
      return;
    }

    pendingHoverTimeout.current = window.setTimeout(() => {
      pendingHoverTimeout.current = null;
      lastHoverProbeAt.current = Date.now();

      if (latestHoverCoordinate.current) {
        runProbe(latestHoverCoordinate.current);
      }
    }, throttleMs - elapsedMs);
  }

  function handleSaveSegmentation() {
    if (!datasetContext.datasetId) {
      setSegmentationSave({
        saving: false,
        result: null,
        error: "Dataset has not been persisted yet.",
      });
      return;
    }

    setSegmentationSave((current) => ({
      ...current,
      saving: true,
      error: null,
    }));

    saveSegmentation(datasetContext.datasetId, threshold)
      .then((result) => {
        setSegmentationSave({
          saving: false,
          result,
          error: null,
        });
        setViewMode("segmentation");
      })
      .catch((error: unknown) => {
        setSegmentationSave({
          saving: false,
          result: null,
          error:
            error instanceof Error
              ? error.message
              : "Unable to save segmentation.",
        });
      });
  }

  function resetViewport() {
    setZoomPercent(100);
    setPanOffset({ x: 0, y: 0 });
  }

  return (
    <main className="workspace">
      <aside className="rail" aria-label="Pipeline context">
        <div className="mark" aria-hidden="true">
          ◈
        </div>
        <div>
          <p className="rail-kicker">Step 2</p>
          <p className="rail-title">CT Preparation</p>
        </div>
        <div className="rail-rule" />
        <span className="status-pill">
          <span aria-hidden="true">●</span> Preview scaffold
        </span>
        <p className="rail-copy">
          Inspect slices, tune a lightweight threshold preview, and prepare the final
          segmentation result for downstream skeletonization.
        </p>
      </aside>

      <section className="content dataset-content">
        <div className="eyebrow">Segmentation</div>
        <h1>CT preparation</h1>
        <p className="lede">
          Review the source volume, preview threshold masks, and save the selected
          segmentation output before skeletonization.
        </p>

        <section className="dataset-panel segmentation-summary" aria-labelledby="segmentation-summary-heading">
          <div className="section-heading">
            <p className="panel-kicker">Dataset context</p>
            <h2 id="segmentation-summary-heading">{datasetContext.dataset}</h2>
          </div>
          <dl className="project-meta">
            <div>
              <dt>Project ID</dt>
              <dd>{datasetContext.projectId}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>
                {datasetContext.dimensions.x}, {datasetContext.dimensions.y},{" "}
                {datasetContext.dimensions.z}
              </dd>
            </div>
            <div>
              <dt>Voxel size</dt>
              <dd>{datasetContext.voxelSizeMicron} micron</dd>
            </div>
            <div>
              <dt>Dataset ID</dt>
              <dd>{datasetContext.datasetId ?? "Not persisted"}</dd>
            </div>
            <div>
              <dt>Preparation status</dt>
              <dd>{preparationStatus}</dd>
            </div>
          </dl>
        </section>

        <div className="segmentation-workbench">
          <section className="dataset-panel view-mode-panel" aria-label="View modes">
            <ViewModeTabs
              value={viewMode}
              onChange={(nextViewMode) => {
                setViewMode(nextViewMode);
                resetViewport();
              }}
            />
          </section>

          <div className="segmentation-grid">
            <SliceViewer
              axis={axis}
              sliceIndex={boundedSliceIndex}
              maxSliceIndex={maxSliceIndex}
              viewMode={viewMode}
              imageUrl={sliceFetch.imageUrl}
              status={sliceFetch.status}
              message={sliceFetch.message}
              zoomPercent={zoomPercent}
              panOffset={panOffset}
              maskPreviewUrl={thresholdPreview.imageUrl}
              maskPreviewLoading={thresholdPreview.status === "loading"}
              overlayEnabled={overlayEnabled}
              overlayOpacity={overlayOpacity}
              onAxisChange={(nextAxis) => {
                setAxis(nextAxis);
                resetViewport();
                setSliceIndex((current) =>
                  Math.min(current, getSliceLimit(nextAxis, datasetContext)),
                );
              }}
              onSliceIndexChange={(nextSliceIndex) => {
                setSliceIndex(nextSliceIndex);
                resetViewport();
              }}
              onProbeClick={handleProbeClick}
              onProbeHover={handleProbeHover}
            />

            <div className="control-stack">
              <ZoomPanControls
                zoomPercent={zoomPercent}
                onZoomIn={() => setZoomPercent((current) => Math.min(400, current + 25))}
                onZoomOut={() =>
                  setZoomPercent((current) => Math.max(25, current - 25))
                }
                onPan={(deltaX, deltaY) =>
                  setPanOffset((current) => ({
                    x: current.x + deltaX,
                    y: current.y + deltaY,
                  }))
                }
                onReset={() => {
                  setZoomPercent(100);
                  setPanOffset({ x: 0, y: 0 });
                }}
              />
              <SegmentationOverlayToggle
                enabled={overlayEnabled}
                opacity={overlayOpacity}
                onChange={setOverlayEnabled}
                onOpacityChange={setOverlayOpacity}
              />
              <VoxelProbe
                coordinate={probe.coordinate}
                intensity={probe.intensity}
                maskValue={probe.maskValue}
              />
            </div>
          </div>

          <div className="dataset-two-column">
            <IntensityHistogram
              minIntensity={thresholdPreview.sliceMinIntensity ?? -0.0031}
              maxIntensity={thresholdPreview.sliceMaxIntensity ?? 0.0153}
              threshold={threshold}
            />
            <ThresholdSlider
              value={threshold}
              min={0.0005}
              max={0.012}
              step={0.0005}
              onChange={setThreshold}
            />
          </div>

          <VoxelCounts
            foreground={thresholdPreview.foreground}
            background={thresholdPreview.background}
          />
          <SaveSegmentationButton
            disabled={!datasetContext.datasetId}
            threshold={threshold}
            saving={segmentationSave.saving}
            result={segmentationSave.result}
            error={segmentationSave.error}
            continueHref={continueHref}
            onSave={handleSaveSegmentation}
          />
        </div>
      </section>
    </main>
  );
}
