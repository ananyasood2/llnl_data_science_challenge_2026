import { useState, useEffect, useMemo } from 'react';
import { Sphere } from '@react-three/drei';

export default function MiniLattice() {
  const [latticeData, setLatticeData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // 1. Fetch the data
  useEffect(() => {
    fetch('http://localhost:8000/api/lattice-graph')
      .then((res) => res.json())
      .then((data) => {
        setLatticeData(data);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching lattice graph:", err);
        setIsLoading(false);
      });
  }, []);

  // 2. High-Performance Strut Calculation
  // We use useMemo so this heavy math only runs once when the data loads.
  const strutPositions = useMemo(() => {
    if (!latticeData || !latticeData.junctions || !latticeData.struts) return null;

    const scale = 0.1;
    const positions = [];
    
    // Create a fast lookup dictionary for junction coordinates by their ID
    const junctionMap = {};
    latticeData.junctions.forEach((j) => {
      junctionMap[j.id] = [
        j.position[0] * scale, 
        j.position[1] * scale, 
        j.position[2] * scale
      ];
    });

    // Build a flat array of [x1, y1, z1, x2, y2, z2, ...] for every strut
    latticeData.struts.forEach((strut) => {
      const p1 = junctionMap[strut.junction0];
      const p2 = junctionMap[strut.junction1];
      
      if (p1 && p2) {
        positions.push(...p1, ...p2);
      }
    });

    // Convert to a Float32Array, which is what the GPU needs for fast rendering
    return new Float32Array(positions);
  }, [latticeData]);

  if (isLoading) {
    return (
      <mesh>
        <boxGeometry args={[2, 2, 2]} />
        <meshBasicMaterial color="yellow" wireframe={true} />
      </mesh>
    );
  }

  if (!latticeData) return null;

  const scale = 0.1;
  const nodeRadius = 0.2; 

  return (
    <group position={[-10, -10, -3]}> 
      
      {/* 3. Render the Nodes (Junctions) */}
      {/* Note: If the browser lags, we will upgrade this to an InstancedMesh later! */}
      {latticeData.junctions.map((junction) => {
        const [x, y, z] = junction.position;
        return (
          <Sphere 
            key={`junction-${junction.id}`} 
            position={[x * scale, y * scale, z * scale]} 
            args={[nodeRadius, 6, 6]} // Extremely low polygon count to prevent lag
          >
            <meshStandardMaterial color="#555555" />
          </Sphere>
        );
      })}

      {/* 4. Render ALL Struts (Edges) at once using high-performance line segments */}
      {strutPositions && (
        <lineSegments>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              count={strutPositions.length / 3}
              array={strutPositions}
              itemSize={3}
            />
          </bufferGeometry>
          <lineBasicMaterial color="cyan" opacity={0.5} transparent={true} />
        </lineSegments>
      )}

    </group>
  );
}