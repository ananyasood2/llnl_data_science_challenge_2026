export const defaultStructureViewerUrl = "http://127.0.0.1:8050";

export type StructureAnalysisSearchParams = Record<
  string,
  string | string[] | undefined
>;

export type StructureEvidenceParams = Partial<
  Record<"datasetId" | "analysisRevision" | "elementKind" | "elementId", string>
>;

const evidenceParamNames = [
  "datasetId",
  "analysisRevision",
  "elementKind",
  "elementId",
] as const;

const safeEvidencePatterns = {
  datasetId: /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/,
  analysisRevision: /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/,
  elementKind: /^(?:strut|node)$/,
  elementId: /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/,
};

export function parseStructureEvidenceParams(
  params: StructureAnalysisSearchParams,
): StructureEvidenceParams {
  const evidence: StructureEvidenceParams = {};

  for (const name of evidenceParamNames) {
    const rawValue = params[name];
    if (rawValue === undefined || (Array.isArray(rawValue) && rawValue.length !== 1)) {
      return {};
    }
    const value = (Array.isArray(rawValue) ? rawValue[0] : rawValue).trim();
    if (!safeEvidencePatterns[name].test(value)) return {};
    evidence[name] = value;
  }

  return evidence;
}

export function getStructureViewerUrl(
  envValue?: string,
  evidence: StructureEvidenceParams = {},
) {
  const value = envValue?.trim();
  const baseUrl = value || defaultStructureViewerUrl;
  const completeRequest = evidenceParamNames.every((name) => {
    const evidenceValue = evidence[name];
    return evidenceValue !== undefined && safeEvidencePatterns[name].test(evidenceValue);
  });
  if (!completeRequest) return baseUrl;

  try {
    const viewerUrl = new URL(baseUrl);
    for (const name of evidenceParamNames) {
      viewerUrl.searchParams.set(name, evidence[name] ?? "");
    }
    viewerUrl.hash = "evidence-panel";
    return viewerUrl.toString();
  } catch {
    return baseUrl;
  }
}
