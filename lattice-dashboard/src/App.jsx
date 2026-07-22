import LatticeViewer from './components/LatticeViewer';
import SidePanel from './components/SidePanel';

function App() {
  return (
    // Flex container to hold both halves of the dashboard
    <div style={{ display: 'flex', width: '100vw', height: '100vh', backgroundColor: '#1a1a1a', color: 'white' }}>
      
      {/* 3D Viewport Area (takes up 75% of the screen) */}
      <div style={{ flex: 3, position: 'relative' }}>
        <LatticeViewer />
      </div>

      {/* Side Panel Area (takes up 25% of the screen) */}
      <div style={{ flex: 1, backgroundColor: '#222', borderLeft: '2px solid #333', overflowY: 'auto' }}>
        <SidePanel />
      </div>

    </div>
  );
}

export default App;