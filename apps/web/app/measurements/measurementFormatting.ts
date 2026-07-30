export type MeasurementStatus = "pass" | "warn" | "fail";

export function formatMicrons(value: number) {
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} µm`;
}

export function formatPercent(value: number) {
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

export function formatVolume(value: number) {
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} mm³`;
}

export function statusLabel(status: MeasurementStatus) {
  return status === "pass" ? "Pass" : status === "warn" ? "Warning" : "Fail";
}

export function thicknessColor(
  thicknessUm: number | null,
  criticalCutoffUm: number,
  targetUm: number,
) {
  if (thicknessUm === null) return "#94a3b8";
  if (thicknessUm < criticalCutoffUm) return "#dc2626";
  if (thicknessUm < targetUm) return "#f59e0b";
  if (thicknessUm > targetUm * 1.3) return "#7c3aed";
  return "#0f9f75";
}

export function clampCutoff(value: number) {
  if (!Number.isFinite(value)) return 350;
  return Math.min(2_000, Math.max(1, value));
}
