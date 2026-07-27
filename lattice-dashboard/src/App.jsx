import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import LatticeViewer from './components/LatticeViewer';
import SidePanel from './components/SidePanel';
import { classifyDefects, fetchLatticeGraph } from './api/dashboardApi.js';
import { DEFAULT_CLASSIFICATION_THRESHOLDS } from './store/useDefectStore.js';

function App() {
  const [selectedStrutId, setSelectedStrutId] = useState(null);
  const {
    data: latticeData = null,
    error: latticeError,
  } = useQuery({
    queryKey: ['lattice-graph'],
    queryFn: fetchLatticeGraph,
  });
  const {
    data: defectsData = null,
    error: defectsError,
  } = useQuery({
    queryKey: ['defects'],
    queryFn: () => classifyDefects(DEFAULT_CLASSIFICATION_THRESHOLDS),
    staleTime: Infinity,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });

  const dashboardError = latticeError || defectsError;

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', backgroundColor: '#1a1a1a', color: 'white' }}>
      <div style={{ flex: 3, position: 'relative' }}>
        {dashboardError && (
          <div
            role="alert"
            style={{
              background: '#5b2121',
              color: '#ffd5d5',
              left: '16px',
              padding: '10px',
              position: 'absolute',
              top: '16px',
              zIndex: 1,
            }}
          >
            Unable to load dashboard data: {dashboardError.message}
          </div>
        )}
        <LatticeViewer 
          latticeData={latticeData} 
          defectsData={defectsData} 
          selectedStrutId={selectedStrutId}
          setSelectedStrutId={setSelectedStrutId}
        />
      </div>

      <div style={{ flex: 1, backgroundColor: '#222', borderLeft: '2px solid #333', overflowY: 'auto' }}>
        <SidePanel 
          defectsData={defectsData} 
          selectedStrutId={selectedStrutId}
          setSelectedStrutId={setSelectedStrutId}
        />
      </div>
    </div>
  );
}

export default App;
