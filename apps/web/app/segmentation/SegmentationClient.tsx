"use client";

/* eslint-disable @next/next/no-img-element */

import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type PointerEvent,
} from "react";
import {
  formatAnalysisStatus,
  formatVoxelSize,
  hasPositiveNumericValue,
  type AnalysisJobStatus,
} from "./analysisFormatting";
import {
  getMarkerPosition,
  getSliceIndexForCoordinate,
  getSliceLimit,
  getVolumeBounds,
  validateVoxelCoordinateInput,
  type Axis,
  type VolumeBounds,
  type VolumeCoordinate,
  type VoxelCoordinateInput,
} from "./coordinateNavigation";
import {
  formatPercent,
  formatVoxelCount,
  getScaledHistogramPath,
  getSegmentationQualityWarnings,
  getThresholdPercent,
  type HistogramScale,
  type HistogramPayload,
  type HistogramScope,
} from "./histogramChart";
import {
  getDefectsEmptyStateMessage,
  getSliceFetchView,
  primaryViewModes,
  segmentationComparisonModes,
  type PrimaryViewMode,
  type SegmentationComparisonMode,
} from "./viewModes";

export type DatasetContext = {
  datasetId: string | null;
  jobId: string | null;
  dataset: string;
  projectId: string;
  dimensions: {
    x: string;
    y: string;
    z: string;
  };
  voxelSizeMicron: string;
  scaleUnit: "micron" | "voxel";
};

type SliceViewerProps = {
  axis: Axis;
  sliceIndex: number;
  maxSliceIndex: number;
  viewMode: PrimaryViewMode;
  comparisonMode: SegmentationComparisonMode;
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
  selectedCoordinate: VolumeCoordinate | null;
  bounds: VolumeBounds;
};

type ViewModeTabsProps = {
  value: PrimaryViewMode;
  onChange: (mode: PrimaryViewMode) => void;
};

type ZoomPanControlsProps = {
  zoomPercent: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onPan: (deltaX: number, deltaY: number) => void;
  onReset: () => void;
};

type SegmentationOverlayToggleProps = {
  comparisonMode: SegmentationComparisonMode;
  enabled: boolean;
  opacity: number;
  onComparisonModeChange: (mode: SegmentationComparisonMode) => void;
  onChange: (enabled: boolean) => void;
  onOpacityChange: (opacity: number) => void;
};

type VoxelProbeProps = {
  headingId: string;
  title: string;
  coordinate: {
    x: number;
    y: number;
    z: number;
  };
  intensity: number | null;
  maskValue: 0 | 1 | null;
};

type VoxelNavigationProps = {
  bounds: VolumeBounds;
  values: VoxelCoordinateInput;
  errors: Partial<Record<keyof VoxelCoordinateInput, string>>;
  onChange: (axis: keyof VoxelCoordinateInput, value: string) => void;
  onSubmit: () => void;
};

type IntensityHistogramProps = {
  histogram: HistogramPayload | null;
  status: HistogramFetchState["status"];
  message: string | null;
  threshold: number;
  scope: HistogramScope;
  scale: HistogramScale;
  onScopeChange: (scope: HistogramScope) => void;
  onScaleChange: (scale: HistogramScale) => void;
};

type ThresholdSliderProps = {
  value: number;
  savedThreshold: number;
  recommendedThreshold: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  onAutoRecommended: () => void;
  onReset: () => void;
};

type VoxelCountsProps = {
  foreground: number | null;
  background: number | null;
};

type SaveSegmentationButtonProps = {
  disabled: boolean;
  threshold: number;
  dirty: boolean;
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

type HistogramFetchState = {
  status: "idle" | "loading" | "ready" | "error";
  payload: HistogramPayload | null;
  message: string | null;
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

type AnalysisJob = {
  job_id: string;
  project_id: string;
  dataset_id: string;
  status: AnalysisJobStatus;
  progress: AnalysisJobStatus[];
  error: string | null;
  scale_unit: "pixels/voxels" | "microns";
  segmentation: {
    threshold: number;
    foreground_voxel_count: number;
    background_voxel_count: number;
    dimensions: { x: number; y: number; z: number };
    mask_path: string;
    slice_preview_path: string;
    summary_path: string;
  } | null;
  skeletonization: {
    skeleton_voxel_count: number;
    connected_components: number;
    endpoints: number;
    branch_points: number;
    disconnected_regions: number;
    bounds: {
      x: [number, number] | null;
      y: [number, number] | null;
      z: [number, number] | null;
      unit: "pixels/voxels" | "microns";
    };
    skeleton_path: string;
    slice_preview_path: string;
    summary_path: string;
  } | null;
};

const defaultThreshold = 0.005;

function clampThreshold(value: number) {
  if (!Number.isFinite(value)) {
    return defaultThreshold;
  }

  return Math.min(1, Math.max(0, value));
}

function formatIntensity(value: number | null) {
  return value === null || !Number.isFinite(value) ? "Pending" : value.toFixed(6);
}

function getAnalysisApiUrl() {
  return process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://localhost:8000";
}

function getSliceUrl(
  datasetId: string,
  axis: Axis,
  sliceIndex: number,
  viewMode: "original" | "segmentation" | "skeleton",
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
  viewMode: "original" | "segmentation" | "skeleton",
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
        : viewMode === "skeleton"
          ? "Skeleton artifact is not available for this dataset."
          : "Segmentation has not been generated for this dataset.";

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

async function fetchIntensityHistogram(
  datasetId: string,
  axis: Axis,
  sliceIndex: number,
  threshold: number,
  scope: HistogramScope,
  signal: AbortSignal,
) {
  const response = await fetch(
    `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(
      datasetId,
    )}/intensity-histogram`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        threshold,
        scope,
        axis: axis.toLowerCase(),
        index: scope === "slice" ? sliceIndex : null,
      }),
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Intensity histogram failed with HTTP ${response.status}.`);
  }

  return (await response.json()) as HistogramPayload;
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

async function fetchLatestAnalysisJob(datasetId: string, signal: AbortSignal) {
  const response = await fetch(
    `${getAnalysisApiUrl()}/v1/datasets/${encodeURIComponent(
      datasetId,
    )}/analysis-jobs/latest`,
    {
      headers: {
        Accept: "application/json",
      },
      signal,
    },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Analysis job fetch failed with HTTP ${response.status}.`);
  }

  return (await response.json()) as AnalysisJob;
}

function ViewModeTabs({ value, onChange }: ViewModeTabsProps) {
  return (
    <div className="view-tabs" role="tablist" aria-label="Slice view mode">
      {primaryViewModes.map((mode) => (
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
    </div>
  );
}

function SliceViewer({
  axis,
  sliceIndex,
  maxSliceIndex,
  viewMode,
  comparisonMode,
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
  selectedCoordinate,
  bounds,
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

  const selectedMarker =
    selectedCoordinate &&
    getSliceIndexForCoordinate(axis, selectedCoordinate) === sliceIndex
      ? selectedCoordinate
      : null;
  const markerPosition = selectedMarker
    ? getMarkerPosition(axis, selectedMarker, bounds)
    : null;

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
        {viewMode === "defects" ? (
          <div className="slice-state slice-state-empty" role="status">
            <strong>Defects unavailable</strong>
            <span>{getDefectsEmptyStateMessage()}</span>
          </div>
        ) : status === "ready" && imageUrl ? (
          <div
            className="slice-image-layer"
            style={{
              transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${
                zoomPercent / 100
              })`,
            }}
          >
            <img
              className="slice-image"
              src={
                viewMode === "segmentation" &&
                comparisonMode === "mask" &&
                maskPreviewUrl
                  ? maskPreviewUrl
                  : imageUrl
              }
              alt={`${viewMode} slice ${sliceIndex} on ${axis} axis`}
              onClick={handleClick}
              onPointerMove={handlePointerMove}
            />
            {overlayEnabled &&
            maskPreviewUrl &&
            viewMode === "segmentation" &&
            comparisonMode === "overlay" ? (
              <img
                className="mask-preview-image"
                src={maskPreviewUrl}
                alt="Threshold mask preview"
                aria-hidden="true"
                style={{
                  opacity: overlayOpacity,
                }}
              />
            ) : null}
            {selectedMarker && markerPosition ? (
              <span
                className="voxel-marker"
                aria-label={`Selected voxel ${selectedMarker.x}, ${selectedMarker.y}, ${selectedMarker.z}`}
                style={{
                  left: `${markerPosition.left}%`,
                  top: `${markerPosition.top}%`,
                }}
              />
            ) : null}
            {maskPreviewLoading ? (
              <span className="mask-loading" role="status">
                Updating mask
              </span>
            ) : null}
          </div>
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
  comparisonMode,
  enabled,
  opacity,
  onComparisonModeChange,
  onChange,
  onOpacityChange,
}: SegmentationOverlayToggleProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="overlay-heading">
      <div className="section-heading">
        <p className="panel-kicker">Segmentation</p>
        <h2 id="overlay-heading">Comparison mode</h2>
      </div>
      <div className="histogram-scope" aria-label="Segmentation comparison mode">
        {segmentationComparisonModes.map((mode) => (
          <button
            type="button"
            key={mode.id}
            className={comparisonMode === mode.id ? "active" : ""}
            aria-pressed={comparisonMode === mode.id}
            onClick={() => onComparisonModeChange(mode.id)}
          >
            {mode.label}
          </button>
        ))}
      </div>
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={enabled}
          disabled={comparisonMode !== "overlay"}
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

function VoxelNavigation({
  bounds,
  values,
  errors,
  onChange,
  onSubmit,
}: VoxelNavigationProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="voxel-nav-heading">
      <div className="section-heading">
        <p className="panel-kicker">Go to voxel</p>
        <h2 id="voxel-nav-heading">Coordinate navigation</h2>
      </div>
      <form className="voxel-nav-form" onSubmit={handleSubmit} noValidate>
        {(["x", "y", "z"] as const).map((coordinateAxis) => (
          <label key={coordinateAxis}>
            <span>
              {coordinateAxis.toUpperCase()} <small>0-{bounds[coordinateAxis]} voxels</small>
            </span>
            <input
              type="number"
              inputMode="numeric"
              step="1"
              min="0"
              max={bounds[coordinateAxis]}
              value={values[coordinateAxis]}
              aria-invalid={errors[coordinateAxis] ? "true" : "false"}
              aria-describedby={
                errors[coordinateAxis] ? `voxel-${coordinateAxis}-error` : undefined
              }
              onChange={(event) => onChange(coordinateAxis, event.target.value)}
            />
            {errors[coordinateAxis] ? (
              <small id={`voxel-${coordinateAxis}-error`} className="inline-error">
                {errors[coordinateAxis]}
              </small>
            ) : null}
          </label>
        ))}
        <button type="submit">Go</button>
      </form>
    </section>
  );
}

function VoxelProbe({
  headingId,
  title,
  coordinate,
  intensity,
  maskValue,
}: VoxelProbeProps) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby={headingId}>
      <div className="section-heading">
        <p className="panel-kicker">Probe</p>
        <h2 id={headingId}>{title}</h2>
      </div>
      <dl className="metric-list selected-voxel-readout">
        <div>
          <dt>Coordinate</dt>
          <dd>
            {coordinate.x}, {coordinate.y}, {coordinate.z}
          </dd>
        </div>
        <div>
          <dt>Intensity</dt>
          <dd>{formatIntensity(intensity)}</dd>
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
  histogram,
  status,
  message,
  threshold,
  scope,
  scale,
  onScopeChange,
  onScaleChange,
}: IntensityHistogramProps) {
  const [hoveredBin, setHoveredBin] = useState<number | null>(null);
  const width = 640;
  const height = 180;
  const counts = histogram?.bin_counts ?? [];
  const displayCounts = getScaledHistogramPath(counts, width, height, scale);
  const edges = histogram?.bin_edges ?? [];
  const visibleCounts =
    scale === "linear" ? counts : counts.map((count) => (count > 0 ? Math.log10(count + 1) : 0));
  const maxCount = Math.max(...visibleCounts, 1);
  const thresholdX = (getThresholdPercent(threshold) / 100) * width;
  const hoveredCount = hoveredBin === null ? null : counts[hoveredBin] ?? null;
  const hoveredStart = hoveredBin === null ? null : edges[hoveredBin] ?? null;
  const hoveredEnd = hoveredBin === null ? null : edges[hoveredBin + 1] ?? null;
  const foreground = histogram?.foreground_voxel_count ?? null;
  const background = histogram?.background_voxel_count ?? null;
  const foregroundPercent = histogram?.foreground_percentage ?? null;
  const backgroundPercent = histogram?.background_percentage ?? null;
  const tooltipLeft =
    hoveredBin === null ? 0 : ((hoveredBin + 0.5) / Math.max(counts.length, 1)) * 100;

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="histogram-heading">
      <div className="section-heading">
        <p className="panel-kicker">Intensity</p>
        <h2 id="histogram-heading">Histogram</h2>
      </div>
      <div className="histogram-scope" aria-label="Histogram scope">
        <button
          type="button"
          className={scope === "volume" ? "active" : ""}
          aria-pressed={scope === "volume"}
          onClick={() => onScopeChange("volume")}
        >
          Full volume
        </button>
        <button
          type="button"
          className={scope === "slice" ? "active" : ""}
          aria-pressed={scope === "slice"}
          onClick={() => onScopeChange("slice")}
        >
          Current slice
        </button>
      </div>
      <div className="histogram-scope" aria-label="Histogram scale">
        <button
          type="button"
          className={scale === "linear" ? "active" : ""}
          aria-pressed={scale === "linear"}
          onClick={() => onScaleChange("linear")}
        >
          Linear
        </button>
        <button
          type="button"
          className={scale === "log" ? "active" : ""}
          aria-pressed={scale === "log"}
          onClick={() => onScaleChange("log")}
        >
          Log
        </button>
      </div>
      <div
        className="histogram"
        role="img"
        aria-label={`256-bin normalized intensity histogram from 0 to 1. Threshold ${threshold.toFixed(
          4,
        )}. Foreground ${formatPercent(foregroundPercent)}; background ${formatPercent(
          backgroundPercent,
        )}.`}
      >
        {status === "error" ? <p className="histogram-status">{message}</p> : null}
        {status === "loading" && !histogram ? (
          <p className="histogram-status">Loading histogram.</p>
        ) : null}
        {histogram ? (
          <>
            <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
              <path className="histogram-area" d={displayCounts} />
              {counts.map((count, index) => {
                const barWidth = width / counts.length;
                const barHeight = ((visibleCounts[index] ?? 0) / maxCount) * height;

                return (
                  <rect
                    key={`${edges[index]}-${index}`}
                    className="histogram-hover-target"
                    x={index * barWidth}
                    y={height - barHeight}
                    width={Math.max(barWidth, 1)}
                    height={Math.max(barHeight, 1)}
                    tabIndex={0}
                    aria-label={`Intensity ${edges[index]?.toFixed(3)} to ${edges[
                      index + 1
                    ]?.toFixed(3)}: ${formatVoxelCount(count)} voxels`}
                    onMouseEnter={() => setHoveredBin(index)}
                    onMouseLeave={() => setHoveredBin(null)}
                    onFocus={() => setHoveredBin(index)}
                    onBlur={() => setHoveredBin(null)}
                  />
                );
              })}
              <line
                className="histogram-threshold-line"
                x1={thresholdX}
                x2={thresholdX}
                y1={0}
                y2={height}
              />
            </svg>
            <div
              className="histogram-threshold-label"
              style={{ left: `${getThresholdPercent(threshold)}%` }}
            >
              Threshold {threshold.toFixed(4)}
            </div>
            {hoveredBin !== null &&
            hoveredStart !== null &&
            hoveredEnd !== null &&
            hoveredCount !== null ? (
              <div className="histogram-tooltip" style={{ left: `${tooltipLeft}%` }}>
                <strong>
                  {hoveredStart.toFixed(3)}-{hoveredEnd.toFixed(3)}
                </strong>
                <span>{formatVoxelCount(hoveredCount)} voxels</span>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
      <div className="histogram-axis" aria-hidden="true">
        <span>0</span>
        <span>Normalized intensity</span>
        <span>1</span>
      </div>
      <dl className="histogram-summary">
        <div>
          <dt>Foreground</dt>
          <dd>
            {formatPercent(foregroundPercent)} ({formatVoxelCount(foreground)})
          </dd>
        </div>
        <div>
          <dt>Background</dt>
          <dd>
            {formatPercent(backgroundPercent)} ({formatVoxelCount(background)})
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ThresholdSlider({
  value,
  savedThreshold,
  recommendedThreshold,
  min,
  max,
  step,
  onChange,
  onAutoRecommended,
  onReset,
}: ThresholdSliderProps) {
  const thresholdId = "threshold-number-input";

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="threshold-heading">
      <div className="section-heading">
        <p className="panel-kicker">Preview threshold</p>
        <h2 id="threshold-heading">Client mask preview</h2>
      </div>
      <label className="threshold-control" htmlFor={thresholdId}>
        <span>Threshold</span>
        <div className="threshold-input-row">
          <input
            id={thresholdId}
            type="number"
            inputMode="decimal"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(event) => onChange(clampThreshold(Number(event.target.value)))}
          />
          <strong>{value.toFixed(6)}</strong>
        </div>
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
      <div className="threshold-actions">
        <button type="button" onClick={onAutoRecommended}>
          Auto recommended {recommendedThreshold.toFixed(4)}
        </button>
        <button type="button" onClick={onReset}>
          Reset to saved {savedThreshold.toFixed(4)}
        </button>
      </div>
    </section>
  );
}

function SegmentationQualityWarnings({
  warnings,
}: {
  warnings: string[];
}) {
  if (warnings.length === 0) {
    return (
      <section className="dataset-panel compact-panel" aria-labelledby="quality-heading">
        <div className="section-heading">
          <p className="panel-kicker">Quality</p>
          <h2 id="quality-heading">Segmentation checks</h2>
        </div>
        <p className="inline-success">Foreground percentage and sensitivity look stable.</p>
      </section>
    );
  }

  return (
    <section className="dataset-panel compact-panel" aria-labelledby="quality-heading">
      <div className="section-heading">
        <p className="panel-kicker">Quality</p>
        <h2 id="quality-heading">Segmentation checks</h2>
      </div>
      <ul className="quality-warnings">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
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

function StructureHandoff({ job }: { job: AnalysisJob | null }) {
  return (
    <section className="dataset-panel compact-panel" aria-labelledby="handoff-heading">
      <div className="section-heading">
        <p className="panel-kicker">Handoff</p>
        <h2 id="handoff-heading">Structure analysis</h2>
      </div>
      {job?.status === "complete" ? (
        <p className="inline-success">
          Ready for structure analysis. Segmentation and skeleton artifacts are
          persisted for dataset {job.dataset_id}.
        </p>
      ) : (
        <p className="field-note">
          Structure analysis handoff becomes available after the backend job completes.
        </p>
      )}
    </section>
  );
}

function SaveSegmentationButton({
  disabled,
  threshold,
  dirty,
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
        <p className={dirty ? "inline-warning" : "inline-success"}>
          {dirty ? "Unsaved threshold change" : "Saved threshold is current"}
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
        <button type="button" disabled={disabled || saving || !dirty} onClick={onSave}>
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
  const [viewMode, setViewMode] = useState<PrimaryViewMode>("original");
  const [comparisonMode, setComparisonMode] =
    useState<SegmentationComparisonMode>("overlay");
  const [overlayEnabled, setOverlayEnabled] = useState(true);
  const [overlayOpacity, setOverlayOpacity] = useState(0.42);
  const [threshold, setThreshold] = useState(defaultThreshold);
  const [savedThreshold, setSavedThreshold] = useState(defaultThreshold);
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
  const [histogramScope, setHistogramScope] = useState<HistogramScope>("volume");
  const [histogramScale, setHistogramScale] = useState<HistogramScale>("linear");
  const [histogramFetch, setHistogramFetch] = useState<HistogramFetchState>({
    status: "idle",
    payload: null,
    message: null,
  });
  const [probe, setProbe] = useState<VoxelProbeProps>({
    headingId: "hover-probe-heading",
    title: "Hovered voxel",
    coordinate: { x: 0, y: 0, z: 0 },
    intensity: null,
    maskValue: null,
  });
  const [selectedProbe, setSelectedProbe] = useState<VoxelProbeProps>({
    headingId: "selected-probe-heading",
    title: "Selected voxel",
    coordinate: { x: 0, y: 0, z: 0 },
    intensity: null,
    maskValue: null,
  });
  const [selectedCoordinate, setSelectedCoordinate] =
    useState<VolumeCoordinate | null>(null);
  const [voxelInput, setVoxelInput] = useState<VoxelCoordinateInput>({
    x: "0",
    y: "0",
    z: "0",
  });
  const [voxelInputErrors, setVoxelInputErrors] = useState<
    Partial<Record<keyof VoxelCoordinateInput, string>>
  >({});
  const [segmentationSave, setSegmentationSave] = useState<{
    saving: boolean;
    result: SavedSegmentation | null;
    error: string | null;
  }>({
    saving: false,
    result: null,
    error: null,
  });
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const [analysisJobError, setAnalysisJobError] = useState<string | null>(null);
  const lastHoverProbeAt = useRef(0);
  const pendingHoverTimeout = useRef<number | null>(null);
  const latestHoverCoordinate = useRef<VolumeCoordinate | null>(null);
  const latestProbeRequestId = useRef(0);
  const probeAbortController = useRef<AbortController | null>(null);
  const latestSelectedProbeRequestId = useRef(0);
  const selectedProbeAbortController = useRef<AbortController | null>(null);
  const maxSliceIndex = getSliceLimit(axis, datasetContext);
  const volumeBounds = getVolumeBounds(datasetContext);
  const boundedSliceIndex = Math.min(sliceIndex, maxSliceIndex);
  const recommendedThreshold =
    analysisJob?.segmentation?.threshold ?? savedThreshold ?? defaultThreshold;
  const thresholdDirty = Math.abs(threshold - savedThreshold) > 1e-9;
  const qualityWarnings = getSegmentationQualityWarnings(histogramFetch.payload);
  const preparationStatus = analysisJob
    ? formatAnalysisStatus(analysisJob.status)
    : segmentationSave.result
      ? "Segmentation saved"
    : segmentationSave.saving
      ? "Saving segmentation"
      : segmentationSave.error || analysisJobError
        ? "Save failed"
        : sliceFetch.status;
  const continueHref =
    datasetContext.datasetId && segmentationSave.result
      ? `/skeletonization?${new URLSearchParams({
          datasetId: datasetContext.datasetId,
          scaleUnit: datasetContext.scaleUnit,
          threshold: String(segmentationSave.result.threshold),
          foregroundVoxelCount: String(segmentationSave.result.foreground_voxel_count),
          backgroundVoxelCount: String(segmentationSave.result.background_voxel_count),
          ...(datasetContext.scaleUnit === "micron" &&
          hasPositiveNumericValue(datasetContext.voxelSizeMicron)
            ? { voxelSizeMicron: datasetContext.voxelSizeMicron }
            : {}),
        }).toString()}`
      : null;

  useEffect(() => {
    if (!datasetContext.datasetId) {
      return;
    }

    const controller = new AbortController();

    fetchLatestAnalysisJob(datasetContext.datasetId, controller.signal)
      .then((job) => {
        if (!job) {
          return;
        }

        setAnalysisJob(job);
        setAnalysisJobError(job.status === "failed" ? job.error : null);

        if (job.segmentation) {
          setThreshold(job.segmentation.threshold);
          setSavedThreshold(job.segmentation.threshold);
          setSegmentationSave({
            saving: false,
            result: {
              status: "saved",
              dataset_id: job.dataset_id,
              threshold: job.segmentation.threshold,
              foreground_voxel_count: job.segmentation.foreground_voxel_count,
              background_voxel_count: job.segmentation.background_voxel_count,
              mask_path: job.segmentation.mask_path,
              slice_preview_path: job.segmentation.slice_preview_path,
              demo_mode: false,
            },
            error: null,
          });
        }

        if (job.segmentation) {
          setViewMode("segmentation");
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }

        setAnalysisJobError(
          error instanceof Error
            ? error.message
            : "Unable to load the latest analysis job.",
        );
      });

    return () => controller.abort();
  }, [datasetContext.datasetId]);

  useEffect(() => {
    let localObjectUrl: string | null = null;

    if (!datasetContext.datasetId) {
      return;
    }

    const sliceView = getSliceFetchView(viewMode, comparisonMode);

    if (!sliceView) {
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
      sliceView,
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
  }, [axis, boundedSliceIndex, comparisonMode, datasetContext.datasetId, viewMode]);

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
    if (!datasetContext.datasetId) {
      return;
    }

    const datasetId = datasetContext.datasetId;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setHistogramFetch((current) => ({
        ...current,
        status: "loading",
        message: "Updating histogram.",
      }));

      fetchIntensityHistogram(
        datasetId,
        axis,
        boundedSliceIndex,
        threshold,
        histogramScope,
        controller.signal,
      )
        .then((payload) => {
          setHistogramFetch({
            status: "ready",
            payload,
            message: null,
          });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) {
            return;
          }

          setHistogramFetch((current) => ({
            ...current,
            status: "error",
            message:
              error instanceof Error
                ? error.message
                : "Unable to update intensity histogram.",
          }));
        });
    }, 175);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [axis, boundedSliceIndex, datasetContext.datasetId, histogramScope, threshold]);

  useEffect(() => {
    return () => {
      if (pendingHoverTimeout.current !== null) {
        window.clearTimeout(pendingHoverTimeout.current);
      }

      probeAbortController.current?.abort();
      selectedProbeAbortController.current?.abort();
    };
  }, []);

  function runHoverProbe(coordinate: VolumeCoordinate) {
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

        setProbe((current) => ({
          headingId: current.headingId,
          title: current.title,
          coordinate: {
            x: nextProbe.x,
            y: nextProbe.y,
            z: nextProbe.z,
          },
          intensity: nextProbe.intensity,
          maskValue: nextProbe.mask_value,
        }));
      })
      .catch(() => {
        if (controller.signal.aborted || requestId !== latestProbeRequestId.current) {
          return;
        }

        setProbe((current) => ({
          ...current,
          coordinate,
          intensity: null,
          maskValue: null,
        }));
      });
  }

  function runSelectedProbe(
    coordinate: VolumeCoordinate,
  ) {
    setSelectedProbe((current) => ({ ...current, coordinate }));

    if (!datasetContext.datasetId) {
      return;
    }

    selectedProbeAbortController.current?.abort();
    const requestId = latestSelectedProbeRequestId.current + 1;
    latestSelectedProbeRequestId.current = requestId;
    const controller = new AbortController();
    selectedProbeAbortController.current = controller;

    fetchVoxelProbe(datasetContext.datasetId, coordinate, threshold, controller.signal)
      .then((nextProbe) => {
        if (requestId !== latestSelectedProbeRequestId.current) {
          return;
        }

        setSelectedProbe((current) => ({
          headingId: current.headingId,
          title: current.title,
          coordinate: {
            x: nextProbe.x,
            y: nextProbe.y,
            z: nextProbe.z,
          },
          intensity: nextProbe.intensity,
          maskValue: nextProbe.mask_value,
        }));
      })
      .catch(() => {
        if (
          controller.signal.aborted ||
          requestId !== latestSelectedProbeRequestId.current
        ) {
          return;
        }

        setSelectedProbe((current) => ({
          ...current,
          coordinate,
          intensity: null,
          maskValue: null,
        }));
      });
  }

  function handleProbeClick(coordinate: VolumeCoordinate) {
    if (pendingHoverTimeout.current !== null) {
      window.clearTimeout(pendingHoverTimeout.current);
      pendingHoverTimeout.current = null;
    }

    lastHoverProbeAt.current = Date.now();
    setSelectedCoordinate(coordinate);
    setVoxelInput({
      x: String(coordinate.x),
      y: String(coordinate.y),
      z: String(coordinate.z),
    });
    setVoxelInputErrors({});
    runSelectedProbe(coordinate);
  }

  function handleProbeHover(coordinate: VolumeCoordinate) {
    latestHoverCoordinate.current = coordinate;
    const now = Date.now();
    const elapsedMs = now - lastHoverProbeAt.current;
    const throttleMs = 80;

    if (elapsedMs >= throttleMs) {
      lastHoverProbeAt.current = now;
      runHoverProbe(coordinate);
      return;
    }

    if (pendingHoverTimeout.current !== null) {
      return;
    }

    pendingHoverTimeout.current = window.setTimeout(() => {
      pendingHoverTimeout.current = null;
      lastHoverProbeAt.current = Date.now();

      if (latestHoverCoordinate.current) {
        runHoverProbe(latestHoverCoordinate.current);
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
        setSavedThreshold(result.threshold);
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

  function handleVoxelNavigation() {
    const validation = validateVoxelCoordinateInput(voxelInput, volumeBounds);
    setVoxelInputErrors(validation.errors);

    if (!validation.valid) {
      return;
    }

    const nextCoordinate = validation.coordinate;
    setSelectedCoordinate(nextCoordinate);
    setSliceIndex(getSliceIndexForCoordinate(axis, nextCoordinate));
    setZoomPercent((current) => Math.max(current, 175));
    setPanOffset({ x: 0, y: 0 });
    runSelectedProbe(nextCoordinate);
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
              <dd>{formatVoxelSize(datasetContext)}</dd>
            </div>
            <div>
              <dt>Measurement unit</dt>
              <dd>{datasetContext.scaleUnit === "micron" ? "Microns" : "Pixels / voxels"}</dd>
            </div>
            <div>
              <dt>Dataset ID</dt>
              <dd>{datasetContext.datasetId ?? "Not persisted"}</dd>
            </div>
            <div>
              <dt>Preparation status</dt>
              <dd>
                {preparationStatus}
                {analysisJob?.error ? `: ${analysisJob.error}` : ""}
              </dd>
            </div>
            <div>
              <dt>Job ID</dt>
              <dd>{analysisJob?.job_id ?? datasetContext.jobId ?? "Not started"}</dd>
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
              comparisonMode={comparisonMode}
              imageUrl={sliceFetch.imageUrl}
              status={sliceFetch.status}
              message={sliceFetch.message}
              zoomPercent={zoomPercent}
              panOffset={panOffset}
              maskPreviewUrl={thresholdPreview.imageUrl}
              maskPreviewLoading={
                viewMode === "segmentation" && thresholdPreview.status === "loading"
              }
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
              selectedCoordinate={selectedCoordinate}
              bounds={volumeBounds}
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
              {viewMode === "segmentation" ? (
                <SegmentationOverlayToggle
                  comparisonMode={comparisonMode}
                  enabled={overlayEnabled}
                  opacity={overlayOpacity}
                  onComparisonModeChange={setComparisonMode}
                  onChange={setOverlayEnabled}
                  onOpacityChange={setOverlayOpacity}
                />
              ) : null}
              <VoxelProbe
                headingId={probe.headingId}
                title={probe.title}
                coordinate={probe.coordinate}
                intensity={probe.intensity}
                maskValue={probe.maskValue}
              />
              <VoxelNavigation
                bounds={volumeBounds}
                values={voxelInput}
                errors={voxelInputErrors}
                onChange={(coordinateAxis, value) => {
                  setVoxelInput((current) => ({
                    ...current,
                    [coordinateAxis]: value,
                  }));
                  setVoxelInputErrors((current) => ({
                    ...current,
                    [coordinateAxis]: undefined,
                  }));
                }}
                onSubmit={handleVoxelNavigation}
              />
              <VoxelProbe
                headingId={selectedProbe.headingId}
                title={selectedProbe.title}
                coordinate={selectedProbe.coordinate}
                intensity={selectedProbe.intensity}
                maskValue={selectedProbe.maskValue}
              />
            </div>
          </div>

          <div className="dataset-two-column">
            <IntensityHistogram
              histogram={histogramFetch.payload}
              status={histogramFetch.status}
              message={histogramFetch.message}
              threshold={threshold}
              scope={histogramScope}
              scale={histogramScale}
              onScopeChange={setHistogramScope}
              onScaleChange={setHistogramScale}
            />
              <ThresholdSlider
              value={threshold}
              savedThreshold={savedThreshold}
              recommendedThreshold={recommendedThreshold}
              min={0}
              max={1}
              step={0.001}
              onChange={(nextThreshold) => {
                setThreshold(clampThreshold(nextThreshold));
                setSegmentationSave((current) => ({
                  ...current,
                  result:
                    Math.abs(clampThreshold(nextThreshold) - savedThreshold) > 1e-9
                      ? null
                      : current.result,
                  error: null,
                }));
              }}
              onAutoRecommended={() => setThreshold(clampThreshold(recommendedThreshold))}
              onReset={() => setThreshold(savedThreshold)}
            />
          </div>

          <VoxelCounts
            foreground={
              histogramFetch.payload?.foreground_voxel_count ??
              thresholdPreview.foreground
            }
            background={
              histogramFetch.payload?.background_voxel_count ??
              thresholdPreview.background
            }
          />
          <SegmentationQualityWarnings warnings={qualityWarnings} />
          <StructureHandoff job={analysisJob} />
          <SaveSegmentationButton
            disabled={!datasetContext.datasetId}
            threshold={threshold}
            dirty={thresholdDirty}
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
