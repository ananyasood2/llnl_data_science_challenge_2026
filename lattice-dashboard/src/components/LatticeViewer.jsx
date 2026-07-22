import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import MiniLattice from './MiniLattice';

export default function LatticeViewer() {
  return (
<div style={{ height: '100%', width: '100%' }}>
          <Canvas camera={{ position: [2, 2, 2], fov: 50 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={1} />
        
        {/* Our 3D Object */}
        <MiniLattice />
        
        {/* Camera Controls */}
        <OrbitControls makeDefault />
        
        {/* Adds a helpful 3D grid to the floor */}
        <gridHelper args={[10, 10]} />
      </Canvas>
    </div>
  );
}
