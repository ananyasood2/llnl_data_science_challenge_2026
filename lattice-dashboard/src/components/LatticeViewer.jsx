import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import MiniLattice from './MiniLattice';
import { useDefectStore } from '../store/useDefectStore.js';
import {
  getEffectiveSourceFilter,
  isDesignIntentAvailable,
  isVisibleDefectScore,
  SOURCE_FILTER_LABELS,
} from '../utils/defectVisibility.js';

const FILTER_OPTIONS = [
  { value: 'ALL', label: 'All Defects' },
  { value: 'MISSING', label: 'Missing' },
  { value: 'BROKEN', label: 'Broken' },
  { value: 'THIN', label: 'Thin' },
];

const SOURCE_FILTER_OPTIONS = [
  { value: 'ALL', label: 'All sources' },
  { value: 'INTENTIONAL', label: 'Intentional design omissions' },
  { value: 'LIKELY_PRINT', label: 'Likely print defects' },
];

function isSelectedStrutVisible(
  defectsData,
  selectedStrutId,
  activeFilter,
  activeSourceFilter,
) {
  const selectedScore = defectsData?.strut_scores?.find(
    (score) => score?.strut_id === selectedStrutId,
  );
  return isVisibleDefectScore(selectedScore, {
    activeFilter,
    activeSourceFilter,
    defectsData,
  });
}

// NEW: A helper component that hooks into the render loop to move the camera
function CameraAnimator({ latticeData, selectedStrutId, controlsRef }) {
  const targetPoint = useMemo(() => {
    if (selectedStrutId === null || !latticeData) return null;

    const strut = latticeData.struts.find((item) => item.id === selectedStrutId);
    if (!strut) return null;

    const j0 = latticeData.junctions.find((junction) => junction.id === strut.junction0);
    const j1 = latticeData.junctions.find((junction) => junction.id === strut.junction1);
    if (!j0 || !j1) return null;

    const scale = 0.1;
    const offsetX = -10;
    const offsetY = -10;
    const offsetZ = -3;
    return new THREE.Vector3(
      ((j0.position[0] + j1.position[0]) / 2) * scale + offsetX,
      ((j0.position[1] + j1.position[1]) / 2) * scale + offsetY,
      ((j0.position[2] + j1.position[2]) / 2) * scale + offsetZ,
    );
  }, [selectedStrutId, latticeData]);

  // 4. Hook into the 3D rendering loop to animate the transition smoothly
  useFrame((state) => {
    if (targetPoint && controlsRef.current) {
      // Smoothly pan the camera's "look at" target to the defect
      controlsRef.current.target.lerp(targetPoint, 0.05);

      // Smoothly zoom the camera in to hover right next to the defect
      const hoverPosition = new THREE.Vector3(targetPoint.x + 2, targetPoint.y + 2, targetPoint.z + 2);
      state.camera.position.lerp(hoverPosition, 0.05);

      controlsRef.current.update();
    }
  });

  return null;
}

export default function LatticeViewer({
  latticeData,
  defectsData,
  selectedStrutId,
  setSelectedStrutId,
}) {
  // We create a reference to the controls so our CameraAnimator can hijack them
  const controlsRef = useRef();
  const activeFilter = useDefectStore((state) => state.activeFilter);
  const activeSourceFilter = useDefectStore((state) => state.activeSourceFilter);
  const setActiveFilter = useDefectStore((state) => state.setActiveFilter);
  const setActiveSourceFilter = useDefectStore((state) => state.setActiveSourceFilter);
  const designIntentAvailable = isDesignIntentAvailable(defectsData);
  const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);
  const designIntentReason = defectsData?.design_intent?.validation?.reason;

  const handleFilterChange = (nextFilter) => {
    if (
      selectedStrutId !== null
      && selectedStrutId !== undefined
      && !isSelectedStrutVisible(
        defectsData,
        selectedStrutId,
        nextFilter,
        effectiveSourceFilter,
      )
    ) {
      setSelectedStrutId(null);
    }
    setActiveFilter(nextFilter);
  };

  const handleSourceFilterChange = (nextSourceFilter) => {
    if (nextSourceFilter !== 'ALL' && !designIntentAvailable) return;
    if (
      selectedStrutId !== null
      && selectedStrutId !== undefined
      && !isSelectedStrutVisible(
        defectsData,
        selectedStrutId,
        activeFilter,
        nextSourceFilter,
      )
    ) {
      setSelectedStrutId(null);
    }
    setActiveSourceFilter(nextSourceFilter);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      <div
        aria-label="Defect type filters"
        style={{
          backgroundColor: '#202020',
          borderBottom: '1px solid #333',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          padding: '12px 16px',
        }}
      >
        {FILTER_OPTIONS.map((filter) => {
          const isActive = activeFilter === filter.value;
          return (
            <button
              key={filter.value}
              type="button"
              aria-pressed={isActive}
              onClick={() => handleFilterChange(filter.value)}
              style={{
                backgroundColor: isActive ? '#244c49' : '#303030',
                border: `1px solid ${isActive ? '#62d5c5' : '#4b5563'}`,
                borderRadius: '999px',
                color: isActive ? '#d7fffb' : '#d1d5db',
                cursor: 'pointer',
                fontWeight: isActive ? 700 : 500,
                padding: '7px 11px',
              }}
            >
              {filter.label}
            </button>
          );
        })}
      </div>

      <div
        aria-label="Defect source filters"
        style={{
          alignItems: 'center',
          backgroundColor: '#1a1a1a',
          borderBottom: '1px solid #333',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
          padding: '10px 16px',
        }}
      >
        {SOURCE_FILTER_OPTIONS.map((filter) => {
          const isDisabled = filter.value !== 'ALL' && !designIntentAvailable;
          const isActive = effectiveSourceFilter === filter.value;
          return (
            <button
              key={filter.value}
              type="button"
              aria-pressed={isActive}
              disabled={isDisabled}
              title={isDisabled ? 'A validated CAD-to-graph registration is required.' : undefined}
              onClick={() => handleSourceFilterChange(filter.value)}
              style={{
                backgroundColor: isActive ? '#43265f' : '#303030',
                border: `1px solid ${isActive ? '#c084fc' : '#4b5563'}`,
                borderRadius: '999px',
                color: isDisabled ? '#737373' : (isActive ? '#f3e8ff' : '#d1d5db'),
                cursor: isDisabled ? 'not-allowed' : 'pointer',
                fontWeight: isActive ? 700 : 500,
                opacity: isDisabled ? 0.6 : 1,
                padding: '7px 11px',
              }}
            >
              {filter.label}
            </button>
          );
        })}
        {!designIntentAvailable && (
          <span role="status" style={{ color: '#ffe2a7', fontSize: '0.85rem', marginLeft: '4px' }}>
            {SOURCE_FILTER_LABELS.INTENTIONAL} and {SOURCE_FILTER_LABELS.LIKELY_PRINT} are unavailable: {designIntentReason ?? 'no validated CAD registration'}.
          </span>
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <Canvas camera={{ position: [5, 5, 5], fov: 50 }} style={{ height: '100%', width: '100%' }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          
          <MiniLattice
            latticeData={latticeData}
            defectsData={defectsData}
            activeFilter={activeFilter}
            activeSourceFilter={effectiveSourceFilter}
          />
          
          {/* Pass the reference down to OrbitControls */}
          <OrbitControls ref={controlsRef} makeDefault />

          {/* Mount our new animator component */}
          <CameraAnimator 
            latticeData={latticeData} 
            selectedStrutId={selectedStrutId}
            controlsRef={controlsRef} 
          />
        </Canvas>
        {selectedStrutId !== null && selectedStrutId !== undefined && (
          <div
            style={{
              position: 'absolute',
              top: '16px',
              left: '16px',
              background: 'rgba(15, 23, 42, 0.86)',
              border: '1px solid #62d5c5',
              borderRadius: '6px',
              color: '#e6fffb',
              fontSize: '0.9rem',
              fontWeight: 700,
              padding: '8px 10px',
              pointerEvents: 'none',
            }}
          >
            Selected strut #{selectedStrutId}
          </div>
        )}
      </div>
    </div>
  );
}
