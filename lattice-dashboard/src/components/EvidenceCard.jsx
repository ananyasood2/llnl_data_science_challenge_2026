const EMPTY_MESSAGE = 'Select a classified defect to view its CT-mask evidence.';

const DEFECT_TYPE_COLORS = {
  MISSING: '#ff4d4f',
  BROKEN: '#ff9f43',
  THIN: '#f9e547',
  INTACT: '#62d5c5',
  UNCLASSIFIED: '#ffbd59',
};

const DEFECT_SOURCE_COLORS = {
  INTENTIONAL_CAD_OMISSION: '#c084fc',
  LIKELY_PRINT_DEFECT: '#ff9f43',
  NOT_A_DYNAMIC_DEFECT: '#62d5c5',
  UNAVAILABLE: '#ffbd59',
};

const DEFECT_SOURCE_LABELS = {
  INTENTIONAL_CAD_OMISSION: 'Intentional CAD omission',
  LIKELY_PRINT_DEFECT: 'Likely print defect',
  NOT_A_DYNAMIC_DEFECT: 'Not a dynamic defect',
  UNAVAILABLE: 'Unavailable',
};

const DESIGN_INTENT_LABELS = {
  INTENTIONAL_CAD_OMISSION: 'Intentional CAD omission',
  CAD_PRESENT: 'CAD-present strut',
  UNAVAILABLE: 'Design map unavailable',
};

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(3) : 'Unavailable';
}

function ScoreRow({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
      <span style={{ color: '#b8b8b8' }}>{label}</span>
      <strong>{formatScore(value)}</strong>
    </div>
  );
}

export default function EvidenceCard({ defectsData, selectedStrutId }) {
  const scores = Array.isArray(defectsData?.strut_scores) ? defectsData.strut_scores : [];
  const selectedScore = scores.find((score) => score?.strut_id === selectedStrutId);

  if (selectedStrutId === null || selectedStrutId === undefined) {
    return (
      <section style={cardStyle}>
        <h3 style={headingStyle}>Selected-Strut Evidence</h3>
        <p style={{ margin: 0, color: '#b8b8b8' }}>{EMPTY_MESSAGE}</p>
      </section>
    );
  }

  if (!selectedScore) {
    return (
      <section style={cardStyle}>
        <h3 style={headingStyle}>Selected-Strut Evidence</h3>
        <p style={{ margin: 0, color: '#ffbd59' }}>
          Evidence for strut #{selectedStrutId} is unavailable in the current analysis results.
        </p>
      </section>
    );
  }

  const flags = selectedScore.flags ?? {};
  const defectType = selectedScore.defect_type ?? 'UNCLASSIFIED';
  const defectSource = selectedScore.defect_source ?? 'UNAVAILABLE';
  const designIntent = selectedScore.design_intent ?? 'UNAVAILABLE';

  return (
    <section style={cardStyle}>
      <h3 style={headingStyle}>Selected-Strut Evidence</h3>
      <p style={{ marginTop: 0 }}>
        <strong>Strut #{selectedScore.strut_id}</strong>
      </p>
      <p
        style={{
          ...statusStyle,
          color: DEFECT_TYPE_COLORS[defectType] ?? DEFECT_TYPE_COLORS.UNCLASSIFIED,
        }}
      >
        Defect Type: {defectType}
      </p>
      <p
        style={{
          ...statusStyle,
          color: DEFECT_SOURCE_COLORS[defectSource] ?? DEFECT_SOURCE_COLORS.UNAVAILABLE,
          marginTop: '-8px',
        }}
      >
        Source: {DEFECT_SOURCE_LABELS[defectSource] ?? defectSource}
      </p>
      <p style={{ color: '#cbd5e1', marginTop: '-8px' }}>
        <strong>As-designed status:</strong> {DESIGN_INTENT_LABELS[designIntent] ?? designIntent}
      </p>

      <div style={{ display: 'grid', gap: '8px' }}>
        <ScoreRow label="Tube occupancy" value={selectedScore.tube_occupancy} />
        <ScoreRow label="Mean local occupancy" value={selectedScore.mean_local_occupancy} />
        <ScoreRow label="Material coverage" value={selectedScore.material_coverage} />
        <ScoreRow
          label="Longest low-material gap"
          value={selectedScore.longest_low_material_gap_fraction}
        />
      </div>

      <div style={{ marginTop: '14px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        <span style={flagStyle(flags.low_occupancy)}>
          Low occupancy: {flags.low_occupancy ? 'yes' : 'no'}
        </span>
        <span style={flagStyle(flags.large_internal_gap)}>
          Large internal gap: {flags.large_internal_gap ? 'yes' : 'no'}
        </span>
      </div>
    </section>
  );
}

const cardStyle = {
  backgroundColor: '#2a2a2a',
  borderRadius: '8px',
  padding: '15px',
};

const headingStyle = {
  marginTop: 0,
  marginBottom: '12px',
};

const statusStyle = {
  fontWeight: 700,
  marginBottom: '14px',
};

function flagStyle(isActive) {
  return {
    backgroundColor: isActive ? '#592c32' : '#263d3b',
    borderRadius: '999px',
    color: isActive ? '#ffb3b3' : '#a9eee6',
    fontSize: '0.8rem',
    padding: '5px 8px',
  };
}
