export type GeometryMetadata = {
  format: "stl-ascii" | "stl-binary";
  triangle_count: number;
  vertex_count: number;
  dimensions: {
    x: number;
    y: number;
    z: number;
  };
  bounds: {
    x: [number, number];
    y: [number, number];
    z: [number, number];
  };
};

export function formatGeometryNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}

export function formatStlFormat(format: GeometryMetadata["format"]) {
  return format === "stl-ascii" ? "ASCII STL" : "Binary STL";
}

export function formatGeometryDimensions(metadata: GeometryMetadata) {
  return ["x", "y", "z"]
    .map((axis) => formatGeometryNumber(metadata.dimensions[axis as "x" | "y" | "z"]))
    .join(" x ");
}

export function formatGeometryBounds(metadata: GeometryMetadata) {
  return (["x", "y", "z"] as const)
    .map((axis) => {
      const [min, max] = metadata.bounds[axis];
      return `${axis}: ${formatGeometryNumber(min)} to ${formatGeometryNumber(max)}`;
    })
    .join("; ");
}
