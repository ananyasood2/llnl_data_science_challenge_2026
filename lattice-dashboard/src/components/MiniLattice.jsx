import { useMemo } from 'react';
import { Sphere } from '@react-three/drei';
import {
  getEffectiveSourceFilter,
  isIntentionalCadOmission,
  isVisibleDefectScore,
} from '../utils/defectVisibility.js';

const DEFECT_COLORS = {
  MISSING: '#ff3333',
  BROKEN: '#ff9500',
  THIN: '#ffe600',
  INTENTIONAL: '#a855f7',
};

function StrutSegments({ positions, color, opacity = 1 }) {
  if (!positions?.length) return null;

  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={positions.length / 3}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <lineBasicMaterial color={color} opacity={opacity} transparent={opacity < 1} />
    </lineSegments>
  );
}

export default function MiniLattice({
  latticeData,
  defectsData,
  activeFilter = 'ALL',
  activeSourceFilter = 'ALL',
}) {
  const {
    intactPositions,
    missingPositions,
    brokenPositions,
    thinPositions,
    intentionalPositions,
  } = useMemo(() => {
    if (!latticeData || !defectsData) {
      return {
        intactPositions: null,
        missingPositions: null,
        brokenPositions: null,
        thinPositions: null,
        intentionalPositions: null,
      };
    }

    const scale = 0.1;
    const effectiveSourceFilter = getEffectiveSourceFilter(activeSourceFilter, defectsData);
    const positionsByType = {
      INTACT: [],
      MISSING: [],
      BROKEN: [],
      THIN: [],
      INTENTIONAL: [],
    };
    const scoreByStrutId = new Map(
      (Array.isArray(defectsData.strut_scores) ? defectsData.strut_scores : []).map((score) => [
        score.strut_id,
        score,
      ]),
    );
    const junctionMap = {};
    latticeData.junctions.forEach((junction) => {
      junctionMap[junction.id] = [
        junction.position[0] * scale,
        junction.position[1] * scale,
        junction.position[2] * scale,
      ];
    });

    latticeData.struts.forEach((strut) => {
      const p1 = junctionMap[strut.junction0];
      const p2 = junctionMap[strut.junction1];
      if (!p1 || !p2) return;

      const score = scoreByStrutId.get(strut.id);
      const defectType = score?.defect_type;
      const type = Object.hasOwn(positionsByType, defectType) ? defectType : 'INTACT';
      const shouldRenderAsDefect = isVisibleDefectScore(score, {
        activeFilter,
        activeSourceFilter: effectiveSourceFilter,
        defectsData,
      });
      const shouldRenderAsIntentional = (
        effectiveSourceFilter === 'INTENTIONAL'
        && shouldRenderAsDefect
        && isIntentionalCadOmission(score)
      );

      if (shouldRenderAsIntentional) {
        positionsByType.INTENTIONAL.push(...p1, ...p2);
      } else if (type === 'INTACT') {
        // Every intact strut stays as muted geometry, even when only one
        // defect subset is being inspected.
        positionsByType.INTACT.push(...p1, ...p2);
      } else if (shouldRenderAsDefect) {
        positionsByType[type].push(...p1, ...p2);
      }
    });

    return {
      intactPositions: new Float32Array(positionsByType.INTACT),
      missingPositions: new Float32Array(positionsByType.MISSING),
      brokenPositions: new Float32Array(positionsByType.BROKEN),
      thinPositions: new Float32Array(positionsByType.THIN),
      intentionalPositions: new Float32Array(positionsByType.INTENTIONAL),
    };
  }, [activeFilter, activeSourceFilter, defectsData, latticeData]);

  // 2. Loading Check (displays yellow wireframe until App.jsx finishes fetching)
  if (!latticeData || !defectsData) {
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
      
      {/* 3. Render Nodes (Junctions) */}
      {latticeData.junctions.map((junction) => (
        <Sphere 
          key={`junction-${junction.id}`} 
          position={[
            junction.position[0] * scale, 
            junction.position[1] * scale, 
            junction.position[2] * scale
          ]} 
          args={[nodeRadius, 6, 6]}
        >
          <meshStandardMaterial color="#555555" />
        </Sphere>
      ))}

      {/* 4. Render intact struts as subdued structural context. */}
      <StrutSegments positions={intactPositions} color="#36d8e6" opacity={0.25} />

      {/* 5. Render only the currently selected dynamic defect categories. */}
      <StrutSegments positions={missingPositions} color={DEFECT_COLORS.MISSING} />
      <StrutSegments positions={brokenPositions} color={DEFECT_COLORS.BROKEN} />
      <StrutSegments positions={thinPositions} color={DEFECT_COLORS.THIN} />
      <StrutSegments positions={intentionalPositions} color={DEFECT_COLORS.INTENTIONAL} />

    </group>
  );
}
