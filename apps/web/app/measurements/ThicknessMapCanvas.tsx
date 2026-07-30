"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { thicknessColor } from "./measurementFormatting";

export type ThicknessMapElement = {
  strut_id: number | string;
  start_xyz: [number, number, number];
  end_xyz: [number, number, number];
  measured_thickness_um: number | null;
  status: string;
};

type Projection = "XY" | "XZ" | "YZ";

function projectionIndices(projection: Projection) {
  if (projection === "XZ") return [0, 2] as const;
  if (projection === "YZ") return [1, 2] as const;
  return [0, 1] as const;
}

export function ThicknessMapCanvas({
  elements,
  criticalCutoffUm,
  targetUm,
  highlightedIds,
}: {
  elements: ThicknessMapElement[];
  criticalCutoffUm: number;
  targetUm: number;
  highlightedIds: Array<number | string>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [projection, setProjection] = useState<Projection>("XY");
  const [zoom, setZoom] = useState(1);
  const [size, setSize] = useState({ width: 900, height: 520 });
  const highlightSet = useMemo(
    () => new Set(highlightedIds.map(String)),
    [highlightedIds],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () =>
      setSize({
        width: Math.max(320, Math.floor(container.clientWidth)),
        height: Math.max(360, Math.min(600, Math.floor(container.clientWidth * 0.58))),
      });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || elements.length === 0) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = size.width * ratio;
    canvas.height = size.height * ratio;
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, size.width, size.height);
    context.fillStyle = "#08131f";
    context.fillRect(0, 0, size.width, size.height);

    const [horizontal, vertical] = projectionIndices(projection);
    const points = elements.flatMap((element) => [element.start_xyz, element.end_xyz]);
    const horizontalValues = points.map((point) => point[horizontal]);
    const verticalValues = points.map((point) => point[vertical]);
    const minHorizontal = Math.min(...horizontalValues);
    const maxHorizontal = Math.max(...horizontalValues);
    const minVertical = Math.min(...verticalValues);
    const maxVertical = Math.max(...verticalValues);
    const spanHorizontal = Math.max(1, maxHorizontal - minHorizontal);
    const spanVertical = Math.max(1, maxVertical - minVertical);
    const padding = 24;
    const scale =
      Math.min(
        (size.width - padding * 2) / spanHorizontal,
        (size.height - padding * 2) / spanVertical,
      ) * zoom;
    const centerHorizontal = (minHorizontal + maxHorizontal) / 2;
    const centerVertical = (minVertical + maxVertical) / 2;
    const project = (point: [number, number, number]) => [
      size.width / 2 + (point[horizontal] - centerHorizontal) * scale,
      size.height / 2 - (point[vertical] - centerVertical) * scale,
    ];

    const regular = elements.filter((item) => !highlightSet.has(String(item.strut_id)));
    const highlighted = elements.filter((item) => highlightSet.has(String(item.strut_id)));
    for (const group of [regular, highlighted]) {
      for (const element of group) {
        const [startX, startY] = project(element.start_xyz);
        const [endX, endY] = project(element.end_xyz);
        const isHighlighted = highlightSet.has(String(element.strut_id));
        context.beginPath();
        context.moveTo(startX, startY);
        context.lineTo(endX, endY);
        context.strokeStyle = isHighlighted
          ? "#ffffff"
          : thicknessColor(
              element.measured_thickness_um,
              criticalCutoffUm,
              targetUm,
            );
        context.globalAlpha = isHighlighted ? 1 : 0.68;
        context.lineWidth = isHighlighted ? 3 : 0.8;
        context.stroke();
      }
    }
    context.globalAlpha = 1;
  }, [criticalCutoffUm, elements, highlightSet, projection, size, targetUm, zoom]);

  return (
    <div className="thickness-map-shell" ref={containerRef}>
      <div className="thickness-map-toolbar">
        <div className="measurement-segmented-control" aria-label="Thickness map projection">
          {(["XY", "XZ", "YZ"] as Projection[]).map((value) => (
            <button
              className={projection === value ? "active" : ""}
              key={value}
              onClick={() => setProjection(value)}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
        <label className="measurement-zoom-control">
          <span>Zoom</span>
          <input
            aria-label="Thickness map zoom"
            max="2"
            min="0.75"
            onChange={(event) => setZoom(Number(event.target.value))}
            step="0.05"
            type="range"
            value={zoom}
          />
        </label>
      </div>
      <canvas aria-label={`${projection} projected strut thickness map`} ref={canvasRef} />
      <div className="thickness-map-legend" aria-label="Thickness color legend">
        <span><i className="thickness-critical" />Below {criticalCutoffUm} µm</span>
        <span><i className="thickness-below-target" />{criticalCutoffUm}–{targetUm} µm</span>
        <span><i className="thickness-nominal" />Near target</span>
        <span><i className="thickness-high" />Above 130% target</span>
        <span><i className="thickness-unmeasured" />Unmeasured</span>
        {highlightedIds.length ? <span><i className="thickness-highlight" />Agent-selected</span> : null}
      </div>
    </div>
  );
}
