import { useMemo, useState } from 'react';
import EvidenceCard from './EvidenceCard';
import RoiEvidenceGallery from './RoiEvidenceGallery';
import { useClassifyDefects } from '../hooks/useClassifyDefects.js';
import { useDefectStore } from '../store/useDefectStore.js';
import {
  getCandidateRowLabel,
  getCandidateSectionLabel,
  getEffectiveSourceFilter,
  isDesignIntentAvailable,
  isVisibleDefectScore,
} from '../utils/defectVisibility.js';

const ROW_HEIGHT = 44;
const LIST_HEIGHT = 352;
const OVERSCAN_ROWS = 6;
const FALLBACK_CALIBRATION_WARNING =
  'Note: Thresholds are currently uncalibrated. Defects shown are provisional candidates.';

function ThresholdControl({ id, label, value, onChange }) {
  return (
    <div style={{ display: 'grid', gap: '6px' }}>
      <label htmlFor={id} style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
        <span>{label}</span>
        <strong>{value.toFixed(2)}</strong>
      </label>
      <input
        id={id}
        type="range"
        min="0"
        max="1"
        step="0.01"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

export default function SidePanel({ defectsData, selectedStrutId, setSelectedStrutId }) {
  const [listScroll, setListScroll] = useState({ filterKey: 'ALL:ALL', top: 0 });
  const missingOccupancyThreshold = useDefectStore(
    (state) => state.missing_occupancy_threshold,
  );
  const brokenGapThreshold = useDefectStore((state) => state.broken_gap_threshold);
  const thinOccupancyThreshold = useDefectStore(
    (state) => state.thin_occupancy_threshold,
  );
  const activeFilter = useDefectStore((state) => state.activeFilter);
  const activeSourceFilter = useDefectStore((state) => state.activeSourceFilter);
  const setMissingOccupancyThreshold = useDefectStore(
    (state) => state.setMissingOccupancyThreshold,
  );
  const setActiveSourceFilter = useDefectStore((state) => state.setActiveSourceFilter);
  const setBrokenGapThreshold = useDefectStore((state) => state.setBrokenGapThreshold);
  const setThinOccupancyThreshold = useDefectStore(
    (state) => state.setThinOccupancyThreshold,
  );
  const {
    mutate: recalculateDefects,
    error: classificationError,
    isError: isClassificationError,
    isPending: isRecalculating,
  } = useClassifyDefects();
  const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);
  const designIntentAvailable = isDesignIntentAvailable(defectsData);
  const filterKey = `${activeFilter}:${effectiveSourceFilter}`;

  const candidateIds = useMemo(
    () => {
      const scores = Array.isArray(defectsData?.strut_scores) ? defectsData.strut_scores : [];
      return scores
        .filter((score) => isVisibleDefectScore(score, {
          activeFilter,
          activeSourceFilter: effectiveSourceFilter,
          defectsData,
        }))
        .map((score) => score.strut_id);
    },
    [activeFilter, defectsData, effectiveSourceFilter],
  );
  const analysisParameters = defectsData?.analysis_parameters ?? {};
  const summary = defectsData?.summary ?? {};
  const calibrationWarning =
    analysisParameters.calibration_warning || FALLBACK_CALIBRATION_WARNING;
  const scrollTop = listScroll.filterKey === filterKey ? listScroll.top : 0;
  const visibleRows = Math.ceil(LIST_HEIGHT / ROW_HEIGHT);
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN_ROWS);
  const endIndex = Math.min(candidateIds.length, startIndex + visibleRows + OVERSCAN_ROWS * 2);
  const visibleCandidateIds = useMemo(
    () => candidateIds.slice(startIndex, endIndex),
    [candidateIds, startIndex, endIndex],
  );

  const handleRecalculate = () => {
    recalculateDefects(undefined, {
      onSuccess: (classificationResult) => {
        const nextSourceFilter = isDesignIntentAvailable(classificationResult)
          ? activeSourceFilter
          : 'ALL';
        if (nextSourceFilter !== activeSourceFilter) {
          setActiveSourceFilter(nextSourceFilter);
        }
        if (selectedStrutId === null || selectedStrutId === undefined) return;

        const selectedScore = classificationResult.strut_scores?.find(
          (score) => score?.strut_id === selectedStrutId,
        );
        if (!isVisibleDefectScore(selectedScore, {
          activeFilter,
          activeSourceFilter: nextSourceFilter,
          defectsData: classificationResult,
        })) {
          setSelectedStrutId(null);
        }
      },
    });
  };

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

      <section style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3 style={{ marginTop: 0 }}>Classification Settings</h3>
        <div style={{ display: 'grid', gap: '14px' }}>
          <ThresholdControl
            id="missing-occupancy-threshold"
            label="Max Occupancy for MISSING"
            value={missingOccupancyThreshold}
            onChange={setMissingOccupancyThreshold}
          />
          <ThresholdControl
            id="broken-gap-threshold"
            label="Min Gap for BROKEN"
            value={brokenGapThreshold}
            onChange={setBrokenGapThreshold}
          />
          <ThresholdControl
            id="thin-occupancy-threshold"
            label="Max Occupancy for THIN"
            value={thinOccupancyThreshold}
            onChange={setThinOccupancyThreshold}
          />
          <button
            type="button"
            onClick={handleRecalculate}
            disabled={isRecalculating}
            style={{
              backgroundColor: isRecalculating ? '#38434f' : '#244c49',
              border: '1px solid #62d5c5',
              borderRadius: '4px',
              color: '#d7fffb',
              cursor: isRecalculating ? 'progress' : 'pointer',
              fontWeight: 700,
              padding: '10px',
            }}
          >
            {isRecalculating ? 'Recalculating…' : 'Recalculate Defects'}
          </button>
          {isClassificationError && (
            <p role="alert" style={{ color: '#ffb3b3', margin: 0 }}>
              Unable to recalculate defects: {classificationError?.message ?? 'Unknown error'}
            </p>
          )}
        </div>
      </section>

      <EvidenceCard defectsData={defectsData} selectedStrutId={selectedStrutId} />

      <RoiEvidenceGallery selectedStrutId={selectedStrutId} />

      {!designIntentAvailable && (
        <p
          role="status"
          style={{ backgroundColor: '#413523', borderRadius: '6px', color: '#ffe2a7', margin: 0, padding: '10px' }}
        >
          Design-source filters are unavailable: {defectsData?.design_intent?.validation?.reason ?? 'no validated CAD registration'}.
        </p>
      )}

      <div style={{ backgroundColor: '#2a2a2a', padding: '15px', borderRadius: '8px' }}>
        <h3>{getCandidateSectionLabel(activeFilter, effectiveSourceFilter, defectsData)}</h3>
        <p style={{ color: '#b8b8b8', marginTop: 0 }}>
          {candidateIds.length} visible candidate{candidateIds.length === 1 ? '' : 's'}. Select one to focus the 3D view and inspect its evidence.
        </p>
        <div
          key={filterKey}
          aria-label={`${getCandidateSectionLabel(activeFilter, effectiveSourceFilter, defectsData)} list`}
          onScroll={(event) => setListScroll({ filterKey, top: event.currentTarget.scrollTop })}
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
                      {getCandidateRowLabel(effectiveSourceFilter, defectsData, id)}
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
