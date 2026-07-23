import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useRef, useEffect, useState } from 'react';
import * as THREE from 'three';
import MiniLattice from './MiniLattice';

// NEW: A helper component that hooks into the render loop to move the camera
function CameraAnimator({ latticeData, focusedDefectId, controlsRef }) {
  const [targetPoint, setTargetPoint] = useState(null);

  useEffect(() => {
    if (focusedDefectId !== null && latticeData) {
      // 1. Find the specific strut in the JSON data
      const strut = latticeData.struts.find(s => s.id === focusedDefectId);
      if (strut) {
        // 2. Find its two connecting nodes
        const j0 = latticeData.junctions.find(j => j.id === strut.junction0);
        const j1 = latticeData.junctions.find(j => j.id === strut.junction1);

        if (j0 && j1) {
          const scale = 0.1;
          // IMPORTANT: We must include the same offset we used in MiniLattice's <group> tag
          const offsetX = -10, offsetY = -10, offsetZ = -3; 

          // 3. Calculate the exact midpoint of the missing strut in world coordinates
          const midX = (((j0.position[0] + j1.position[0]) / 2) * scale) + offsetX;
          const midY = (((j0.position[1] + j1.position[1]) / 2) * scale) + offsetY;
          const midZ = (((j0.position[2] + j1.position[2]) / 2) * scale) + offsetZ;

          setTargetPoint(new THREE.Vector3(midX, midY, midZ));
        }
      }
    }
  }, [focusedDefectId, latticeData]);

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

export default function LatticeViewer({ latticeData, defectsData, focusedDefectId }) {
  // We create a reference to the controls so our CameraAnimator can hijack them
  const controlsRef = useRef();

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <Canvas camera={{ position: [5, 5, 5], fov: 50 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={1} />
        
        <MiniLattice latticeData={latticeData} defectsData={defectsData} />
        
        {/* Pass the reference down to OrbitControls */}
        <OrbitControls ref={controlsRef} makeDefault />

        {/* Mount our new animator component */}
        <CameraAnimator 
          latticeData={latticeData} 
          focusedDefectId={focusedDefectId} 
          controlsRef={controlsRef} 
        />
      </Canvas>
    </div>
  );
}
