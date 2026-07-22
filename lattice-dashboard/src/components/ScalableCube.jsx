export default function ScalableCube({ scale = 1 }) {
  return (
    <mesh scale={scale}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="cyan" wireframe={true} />
    </mesh>
  );
}