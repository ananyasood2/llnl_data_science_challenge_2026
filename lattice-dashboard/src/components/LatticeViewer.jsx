import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import MiniLattice from './MiniLattice';

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

export default function LatticeViewer({ latticeData, defectsData, selectedStrutId }) {
  // We create a reference to the controls so our CameraAnimator can hijack them
  const controlsRef = useRef();

  return (
    <div style={{ height: '100%', position: 'relative', width: '100%' }}>
      <Canvas camera={{ position: [5, 5, 5], fov: 50 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={1} />
        
        <MiniLattice latticeData={latticeData} defectsData={defectsData} />
        
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
  );
}
