const API_ORIGIN = 'http://localhost:8000';

async function requestJson(path, options) {
  const response = await fetch(`${API_ORIGIN}${path}`, options);
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail;
    throw new Error(detail || `Request failed with status ${response.status}.`);
  }

  return payload;
}

export function fetchLatticeGraph() {
  return requestJson('/api/lattice-graph');
}

export function fetchDefects() {
  return requestJson('/api/analyze-defects');
}

export function classifyDefects(thresholds) {
  return requestJson('/api/classify_defects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(thresholds),
  });
}
