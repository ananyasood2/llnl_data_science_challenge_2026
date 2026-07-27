export const TYPE_FILTER_OPTIONS = Object.freeze(['ALL', 'MISSING', 'BROKEN', 'THIN']);
export const SOURCE_FILTER_OPTIONS = Object.freeze(['ALL', 'INTENTIONAL', 'LIKELY_PRINT']);

export const TYPE_FILTER_LABELS = Object.freeze({
  ALL: 'All Defects',
  MISSING: 'Missing',
  BROKEN: 'Broken',
  THIN: 'Thin',
});

export const SOURCE_FILTER_LABELS = Object.freeze({
  ALL: 'All sources',
  INTENTIONAL: 'Intentional design omissions',
  LIKELY_PRINT: 'Likely print defects',
});

export function isDesignIntentAvailable(defectsData) {
  return defectsData?.design_intent?.status === 'validated';
}

export function getEffectiveSourceFilter(activeSourceFilter, defectsData) {
  if (!isDesignIntentAvailable(defectsData)) return 'ALL';
  return SOURCE_FILTER_OPTIONS.includes(activeSourceFilter) ? activeSourceFilter : 'ALL';
}

function matchesDynamicType(score, activeFilter) {
  const defectType = score?.defect_type;
  if (!defectType || defectType === 'INTACT') return false;
  return activeFilter === 'ALL' || defectType === activeFilter;
}

export function isIntentionalCadOmission(score) {
  return (
    score?.design_intent === 'INTENTIONAL_CAD_OMISSION'
    || score?.defect_source === 'INTENTIONAL_CAD_OMISSION'
  );
}

/**
 * The single shared visibility rule for the candidate list, selection, and 3D
 * rendering. Intentional CAD omissions are deliberately independent from the
 * dynamic type filter, since an as-designed omission can be CT-classified as
 * INTACT yet still needs to be visible as a CAD reference.
 */
export function isVisibleDefectScore(
  score,
  { activeFilter = 'ALL', activeSourceFilter = 'ALL', defectsData } = {},
) {
  const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);

  if (effectiveSourceFilter === 'INTENTIONAL') {
    return isIntentionalCadOmission(score);
  }

  if (effectiveSourceFilter === 'LIKELY_PRINT') {
    return (
      score?.defect_source === 'LIKELY_PRINT_DEFECT'
      && matchesDynamicType(score, activeFilter)
    );
  }

  return matchesDynamicType(score, activeFilter);
}

export function getCandidateSectionLabel(activeFilter, activeSourceFilter, defectsData) {
  const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);
  if (effectiveSourceFilter === 'INTENTIONAL') return 'Intentional CAD Omission IDs';
  if (effectiveSourceFilter === 'LIKELY_PRINT') {
    return activeFilter === 'ALL'
      ? 'Likely Print-Defect IDs'
      : `Likely Print ${TYPE_FILTER_LABELS[activeFilter]} IDs`;
  }
  return `${TYPE_FILTER_LABELS[activeFilter] ?? TYPE_FILTER_LABELS.ALL} Candidate IDs`;
}

export function getCandidateRowLabel(activeSourceFilter, defectsData, strutId) {
  const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);
  if (effectiveSourceFilter === 'INTENTIONAL') return `Intentional CAD omission strut #${strutId}`;
  if (effectiveSourceFilter === 'LIKELY_PRINT') return `Likely print-defect strut #${strutId}`;
  return `Candidate strut #${strutId}`;
}
