import { useMemo, useState } from 'react';
import EvidenceCard from './EvidenceCard';

const ROW_HEIGHT = 44;
const LIST_HEIGHT = 352;
const OVERSCAN_ROWS = 6;
const FALLBACK_CALIBRATION_WARNING =
  'Note: Thresholds are currently uncalibrated. Defects shown are provisional candidates.';

export default function SidePanel({ defectsData, selectedStrutId, setSelectedStrutId }) {
  const [scrollTop, setScrollTop] = useState(0);

  const candidateIds = useMemo(
    () => (Array.isArray(defectsData?.defective_strut_ids) ? defectsData.defective_strut_ids : []),
    [defectsData],
  );
  const analysisParameters = defectsData?.analysis_parameters ?? {};
  const summary = defectsData?.summary ?? {};
  const calibrationWarning =
    analysisParameters.calibration_warning || FALLBACK_CALIBRATION_WARNING;
  const visibleRows = Math.ceil(LIST_HEIGHT / ROW_HEIGHT);
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_ROWS);
  const endIndex = Math.min(candidateIds.length, startIndex + visibleRows + OVERSCAN_ROWS * 2);
  const visibleCandidateIds = useMemo(
    () => candidateIds.slice(startIndex, endIndex),
    [candidateIds, startIndex, endIndex],
  );

  if (!defectsData) return <div style={{ padding: '20px' }}>Loading Diagnostics...</div>;

  return (
    <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h2>Lattice Diagnostics</h2>

      <div
        role="status"
        style={{
          backgroundColor: '#5b4121',
          border: '1px solid #ffbd59',
          borderRadius: '8px',
          color: '#ffe2a7',
          padding: '12px',
        }}
      >
        {calibrationWarning}
      </div>
      
      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Defect Summary</h3>
        <p><strong>Status:</strong> {defectsData.status}</p>
        <p><strong>Total Expected Struts:</strong> {summary.total_expected_struts ?? 'Unavailable'}</p>
        <p><strong>Candidate Struts:</strong> <span style={{ color: '#ff8888', fontWeight: 'bold' }}>{summary.missing_defects_count ?? 'Unavailable'}</span></p>
        <p><strong>Defect Percentage:</strong> {summary.defect_percentage ?? 'Unavailable'}</p>
      </div>

      <EvidenceCard defectsData={defectsData} selectedStrutId={selectedStrutId} />

      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Provisional Candidate IDs</h3>
        <p style={{ color: '#b8b8b8', marginTop: 0 }}>
          Select a candidate to focus the 3D view and inspect its evidence.
        </p>
        <div
          aria-label="Provisional candidate strut IDs"
          onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
          style={{
            border: '1px solid #444',
            borderRadius: '6px',
            height: `${LIST_HEIGHT}px`,
            overflowY: 'auto',
          }}
        >
          {candidateIds.length ? (
            <div style={{ height: `${candidateIds.length * ROW_HEIGHT}px`, position: 'relative' }}>
              <div style={{ position: 'absolute', top: `${startIndex * ROW_HEIGHT}px`, left: 0, right: 0 }}>
                {visibleCandidateIds.map((id) => {
                  const isSelected = id === selectedStrutId;
                  return (
                    <button
                      key={id}
                      onClick={() => setSelectedStrutId(id)}
                      style={{
                        alignItems: 'center',
                        backgroundColor: isSelected ? '#244c49' : 'transparent',
                        border: 'none',
                        borderBottom: '1px solid #444',
                        color: isSelected ? '#a9eee6' : '#c7d2fe',
                        cursor: 'pointer',
                        display: 'flex',
                        fontWeight: isSelected ? 700 : 600,
                        height: `${ROW_HEIGHT}px`,
                        padding: '0 12px',
                        textAlign: 'left',
                        width: '100%',
                      }}
                    >
                      Candidate strut #{id}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <p style={{ color: '#b8b8b8', padding: '12px' }}>No candidate strut IDs are available.</p>
          )}
        </div>
      </div>

      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>Agent Co-Pilot</h3>
        <input 
          type="text" 
          placeholder="Ask about the defects..." 
          style={{ width: '100%', padding: '10px', borderRadius: '4px', border: 'none' }}
        />
      </div>
    </div>
  );
}
