export const defaultStructureViewerUrl = "http://127.0.0.1:8050";

export function getStructureViewerUrl(envValue?: string) {
  const value = envValue?.trim();
  return value || defaultStructureViewerUrl;
}
