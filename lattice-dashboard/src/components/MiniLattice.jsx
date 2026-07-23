import { useState, useEffect, useMemo } from 'react';
import { Sphere } from '@react-three/drei';

export default function MiniLattice() {
  const [latticeData, setLatticeData] = useState(null);
  const [defectsData, setDefectsData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // 1. Fetch BOTH the Lattice Graph and the Defects List
  useEffect(() => {
    Promise.all([
      fetch('http://localhost:8000/api/lattice-graph').then(res => res.json()),
      fetch('http://localhost:8000/api/analyze-defects').then(res => res.json())
    ])
    .then(([lattice, defects]) => {
      setLatticeData(lattice);
      setDefectsData(defects);
      setIsLoading(false);
    })
    .catch((err) => {
      console.error("Error fetching data:", err);
      setIsLoading(false);
    });
  }, []);

  // 2. High-Performance Array Splitting
  const { healthyPositions, defectivePositions } = useMemo(() => {
    if (!latticeData || !defectsData) return { healthyPositions: null, defectivePositions: null };

    const scale = 0.1;
    const healthy = [];
    const defective = [];
    
    // Create a Set of defective IDs for super fast lookup
    const defectiveSet = new Set(defectsData.defective_strut_ids);
    
    const junctionMap = {};
    latticeData.junctions.forEach((j) => {
      junctionMap[j.id] = [j.position[0] * scale, j.position[1] * scale, j.position[2] * scale];
    });

    // Split the struts based on whether their ID is in the defective Set
    latticeData.struts.forEach((strut) => {
      const p1 = junctionMap[strut.junction0];
      const p2 = junctionMap[strut.junction1];
      
      if (p1 && p2) {
        if (defectiveSet.has(strut.id)) {
          defective.push(...p1, ...p2); // Send to the Red array
        } else {
          healthy.push(...p1, ...p2);   // Send to the Cyan array
        }
      }
    });

    return {
      healthyPositions: new Float32Array(healthy),
      defectivePositions: new Float32Array(defective)
    };
  }, [latticeData, defectsData]);

  if (isLoading) {
    return (
      <mesh>
        <boxGeometry args={[2, 2, 2]} />
        <meshBasicMaterial color="yellow" wireframe={true} />
      </mesh>
    );
  }

  const scale = 0.1;
  const nodeRadius = 0.2; 

  return (
    <group position={[-10, -10, -3]}> 
      
      {/* 3. Render Nodes */}
      {latticeData.junctions.map((junction) => (
        <Sphere 
          key={`junction-${junction.id}`} 
          position={[junction.position[0] * scale, junction.position[1] * scale, junction.position[2] * scale]} 
          args={[nodeRadius, 6, 6]}
        >
          <meshStandardMaterial color="#555555" />
        </Sphere>
      ))}

      {/* 4. Render Healthy Struts (Cyan) */}
      {healthyPositions && (
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={healthyPositions.length / 3}
              array={healthyPositions}
              itemSize={3}
            />
          </bufferGeometry>
          <lineBasicMaterial color="cyan" opacity={0.3} transparent={true} />
        </lineSegments>
      )}

      {/* 5. Render Defective Struts (Red & Thicker) */}
      {defectivePositions && (
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={defectivePositions.length / 3}
              array={defectivePositions}
              itemSize={3}
            />
          </bufferGeometry>
          {/* We use a glowing red color so they pop out! */}
          <lineBasicMaterial color="#ff0000" linewidth={3} />
        </lineSegments>
      )}

    </group>
  );
}