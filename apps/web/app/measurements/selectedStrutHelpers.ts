export const SELECTED_STRUT_COPILOT_QUESTION =
  "Explain the deterministic thickness evidence for the selected strut, including how it compares with the 350 µm target, the 300 µm critical cutoff, and the active user cutoff. Report its population percentile and compare it with its immediate one-hop topology neighbors. Cite the qualified analysis revision and tool run, state if the strut is unmeasured, do not infer spatial isolation or clustering from the one-hop comparison, and do not make an engineering acceptance decision.";

export type SelectedHistogramMarker =
  | { kind: "unmeasured" }
  | { kind: "visible" | "overflow"; position: number; valueUm: number };

export function normalizeStrutId(value: string) {
  const normalized = value.trim();
  if (
    normalized.length === 0 ||
    normalized.length > 128 ||
    !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

export function buildStrutEvidenceHref(
  datasetId: string,
  analysisRevision: string,
  strutId: number | string,
) {
  const query = new URLSearchParams({
    datasetId,
    analysisRevision,
    elementKind: "strut",
    elementId: String(strutId),
  });
  return `/structure-analysis?${query.toString()}`;
}

export function analysisRevisionsMatch(
  expectedRevision: string,
  actualRevision: string,
) {
  return expectedRevision.length > 0 && expectedRevision === actualRevision;
}

export function getSelectedHistogramMarker(
  measuredThicknessUm: number | null,
  rangeMaxUm: number,
): SelectedHistogramMarker {
  if (measuredThicknessUm === null || !Number.isFinite(measuredThicknessUm)) {
    return { kind: "unmeasured" };
  }
  const safeRangeMax = Math.max(1, rangeMaxUm);
  if (measuredThicknessUm > safeRangeMax) {
    return { kind: "overflow", position: 1, valueUm: measuredThicknessUm };
  }
  return {
    kind: "visible",
    position: Math.min(1, Math.max(0, measuredThicknessUm / safeRangeMax)),
    valueUm: measuredThicknessUm,
  };
}
