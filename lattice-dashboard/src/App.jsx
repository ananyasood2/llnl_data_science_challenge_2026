import { useState, useEffect } from 'react';
import LatticeViewer from './components/LatticeViewer';
import SidePanel from './components/SidePanel';

function App() {
  const [latticeData, setLatticeData] = useState(null);
  const [defectsData, setDefectsData] = useState(null);
  
  const [selectedStrutId, setSelectedStrutId] = useState(null);

  useEffect(() => {
    Promise.all([
      fetch('http://localhost:8000/api/lattice-graph').then(res => res.json()),
      fetch('http://localhost:8000/api/analyze-defects').then(res => res.json())
    ])
    .then(([lattice, defects]) => {
      setLatticeData(lattice);
      setDefectsData(defects);
    })
    .catch(err => console.error("Error fetching data:", err));
  }, []);

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', backgroundColor: '#1a1a1a', color: 'white' }}>
      <div style={{ flex: 3, position: 'relative' }}>
        <LatticeViewer 
          latticeData={latticeData} 
          defectsData={defectsData} 
          selectedStrutId={selectedStrutId}
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
