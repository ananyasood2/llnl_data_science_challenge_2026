"use client";
/* eslint-disable react-hooks/exhaustive-deps */

import { useEffect, useRef } from "react";

export type Visibility = Record<"missing" | "disconnected" | "thin" | "broken" | "clear", boolean>;

export default function ThreeLatticeViewer({ visible, slice, variant = "overlay", runId, onSelectStrut }: { visible: Visibility; slice: number; variant?: "tiff" | "json" | "overlay"; runId?: string; onSelectStrut?: (strut: { id: number; classification: string; support: number; gap: number; a: number[]; b: number[] }) => void }) {
  const mount = useRef<HTMLDivElement>(null);
  const canvasHost = useRef<HTMLDivElement>(null);
  const groups = useRef<Record<string, { visible: boolean }>>({});
  const slicePlane = useRef<import("three").Mesh | null>(null);
  const sliceBounds = useRef<{ min: number; max: number } | null>(null);

  useEffect(() => { Object.entries(visible).forEach(([name, value]) => { if (groups.current[name]) groups.current[name].visible = value; }); }, [visible]);
  useEffect(() => { if (slicePlane.current) { const target = slice * 0.04903225806451613; const bounds = sliceBounds.current; slicePlane.current.position.z = bounds ? Math.min(bounds.max, Math.max(bounds.min, target)) : target; } }, [slice]);
  useEffect(() => {
    let clean = false, renderer: import("three").WebGLRenderer | undefined, frame = 0;
    const run = async () => {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      const response = await fetch(runId ? `/api/viewer?run=${encodeURIComponent(runId)}` : "/api/viewer"); if (!response.ok) throw new Error(`Geometry request failed (${response.status})`); const data = await response.json(); if (clean || !mount.current || !canvasHost.current) return;
      if (!Array.isArray(data.nodes) || !Array.isArray(data.struts) || data.nodes.length === 0) throw new Error("Viewer data is incomplete: expected nodes and struts.");
      data.nodes = data.nodes.filter((point: unknown) => Array.isArray(point) && point.length >= 3 && point.slice(0, 3).every(Number.isFinite));
      data.struts = data.struts.filter((strut: { a?: unknown; b?: unknown; classification?: string }) => Array.isArray(strut.a) && Array.isArray(strut.b) && strut.a.length >= 3 && strut.b.length >= 3 && strut.a.slice(0, 3).every(Number.isFinite) && strut.b.slice(0, 3).every(Number.isFinite) && ["clear", "missing", "disconnected", "broken", "thin"].includes(strut.classification ?? ""));
      if (data.nodes.length === 0 || data.struts.length === 0) throw new Error("Viewer data contains no valid geometry.");
      const scale = data.scale.voxel_size_mm as number;
      const bounds = new THREE.Box3(); data.nodes.forEach((point: number[]) => bounds.expandByPoint(new THREE.Vector3(point[0] * scale, point[1] * scale, point[2] * scale)));
      const centre = bounds.getCenter(new THREE.Vector3()); const extent = bounds.getSize(new THREE.Vector3()); const largestAxis = Math.max(extent.x, extent.y, extent.z);
      const scene = new THREE.Scene(); scene.background = new THREE.Color("#e7eeea"); scene.fog = new THREE.Fog("#e7eeea", largestAxis * 4, largestAxis * 9);
      const camera = new THREE.PerspectiveCamera(45, mount.current.clientWidth / mount.current.clientHeight, .01, 500); camera.position.copy(centre).add(new THREE.Vector3(largestAxis * 1.15, largestAxis * .85, largestAxis * 1.35));
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" }); renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.setClearColor("#e7eeea"); canvasHost.current.replaceChildren(renderer.domElement);
      const tooltip = document.createElement("div"); tooltip.className = "three-tooltip"; canvasHost.current.appendChild(tooltip);
      scene.add(new THREE.AmbientLight(0xffffff, 1.3)); const key = new THREE.DirectionalLight(0xffffff, 2.5); key.position.set(22, 35, 18); scene.add(key);
      const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true; controls.minDistance = largestAxis * .45; controls.maxDistance = largestAxis * 4; controls.target.copy(centre); controls.update();
      const colors: Record<string, string> = variant === "json" ? { clear: "#4f7899", missing: "#4f7899", disconnected: "#4f7899", broken: "#4f7899", thin: "#4f7899" } : variant === "tiff" ? { clear: "#4c9288", missing: "#5aa99d", disconnected: "#5aa99d", broken: "#5aa99d", thin: "#5aa99d" } : { clear: "#26836f", missing: "#e65c43", disconnected: "#d49536", broken: "#bf7947", thin: "#9074c6" };
      const buckets: Record<string, typeof data.struts> = { clear: [], missing: [], disconnected: [], broken: [], thin: [] }; data.struts.forEach((strut: typeof data.struts[number]) => buckets[strut.classification].push(strut));
      const up = new THREE.Vector3(0, 1, 0); const midpoint = new THREE.Vector3(), direction = new THREE.Vector3();
      Object.entries(buckets).forEach(([name, struts]) => {
        const group = new THREE.Group(); groups.current[name] = group; scene.add(group);
        const geometry = new THREE.CylinderGeometry(1, 1, 1, 8, 1); const material = new THREE.MeshStandardMaterial({ color: colors[name], roughness: .58, metalness: .05, transparent: variant !== "json" || name !== "clear", opacity: variant === "json" ? .72 : name === "clear" ? .62 : .98 });
        const mesh = new THREE.InstancedMesh(geometry, material, struts.length); const matrix = new THREE.Matrix4(); const quaternion = new THREE.Quaternion(); const size = new THREE.Vector3();
        struts.forEach((strut: typeof data.struts[number], index: number) => {
          const a = new THREE.Vector3(strut.a[0] * scale, strut.a[1] * scale, strut.a[2] * scale); const b = new THREE.Vector3(strut.b[0] * scale, strut.b[1] * scale, strut.b[2] * scale); direction.subVectors(b, a); const length = direction.length(); if (length < 1e-6) { matrix.makeScale(0, 0, 0); mesh.setMatrixAt(index, matrix); return; } midpoint.addVectors(a, b).multiplyScalar(.5); quaternion.setFromUnitVectors(up, direction.normalize());
          const radius = .075 * (name === "thin" ? Math.max(.35, Math.sqrt(strut.support)) : 1); size.set(radius, length, radius); matrix.compose(midpoint, quaternion, size); mesh.setMatrixAt(index, matrix);
          if (variant === "tiff") mesh.setColorAt(index, new THREE.Color(colors[name]).multiplyScalar(.45 + strut.support * .65));
          else if (variant === "overlay" && name !== "clear") mesh.setColorAt(index, new THREE.Color(colors[name]).multiplyScalar(.65 + strut.confidence * .35));
        }); mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true; mesh.userData.struts = struts; group.add(mesh);
        if (name !== "clear") {
          const markerRadius = name === "missing" ? .26 : name === "disconnected" ? .21 : name === "broken" ? .19 : .17;
          const markerGeometry = new THREE.SphereGeometry(markerRadius, 10, 8);
          const markerMaterial = new THREE.MeshStandardMaterial({ color: colors[name], roughness: .35, metalness: .08, emissive: new THREE.Color(colors[name]).multiplyScalar(.18) });
          const markers = new THREE.InstancedMesh(markerGeometry, markerMaterial, struts.length * 2);
          const markerMatrix = new THREE.Matrix4();
          struts.forEach((strut: typeof data.struts[number], index: number) => {
            const a = new THREE.Vector3(strut.a[0] * scale, strut.a[1] * scale, strut.a[2] * scale);
            const b = new THREE.Vector3(strut.b[0] * scale, strut.b[1] * scale, strut.b[2] * scale);
            markerMatrix.setPosition(a); markers.setMatrixAt(index * 2, markerMatrix);
            markerMatrix.setPosition(b); markers.setMatrixAt(index * 2 + 1, markerMatrix);
          });
          markers.instanceMatrix.needsUpdate = true;
          group.add(markers);
        }
      });
      const sphereGeometry = new THREE.SphereGeometry(.095, 8, 6); const sphereMaterial = new THREE.MeshStandardMaterial({ color: "#dbe8e4", roughness: .5 }); const nodes = new THREE.InstancedMesh(sphereGeometry, sphereMaterial, data.nodes.length); const nodeMatrix = new THREE.Matrix4(); data.nodes.forEach((point: number[], index: number) => { nodeMatrix.setPosition(point[0] * scale, point[1] * scale, point[2] * scale); nodes.setMatrixAt(index, nodeMatrix); }); nodes.instanceMatrix.needsUpdate = true; scene.add(nodes);
      const plane = new THREE.Mesh(new THREE.PlaneGeometry(Math.max(extent.x, extent.y) * 1.1, Math.max(extent.x, extent.y) * 1.1), new THREE.MeshBasicMaterial({ color: "#d6f0e8", transparent: true, opacity: .16, side: THREE.DoubleSide, depthWrite: false })); sliceBounds.current = { min: bounds.min.z, max: bounds.max.z }; plane.position.z = Math.min(bounds.max.z, Math.max(bounds.min.z, slice * scale)); scene.add(plane); slicePlane.current = plane;
      const resizeRenderer = (width: number, height: number) => {
        if (!renderer || width === 0 || height === 0) return;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
      };
      const resizeObserver = new ResizeObserver(([entry]) => {
        resizeRenderer(entry.contentRect.width, entry.contentRect.height);
      });
      resizeObserver.observe(mount.current);
      const initialLayoutFrame = requestAnimationFrame(() => {
        const rect = mount.current?.getBoundingClientRect();
        if (rect) resizeRenderer(rect.width, rect.height);
      });
      const animate = () => { frame = requestAnimationFrame(animate); controls.update(); renderer?.render(scene, camera); }; animate();
      const raycaster = new THREE.Raycaster(); const pointer = new THREE.Vector2();
      const hover = (event: PointerEvent) => {
        const rect = renderer!.domElement.getBoundingClientRect(); pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1; pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObjects(scene.children, true).find(item => Array.isArray(item.object.userData.struts) && item.instanceId !== undefined);
        if (!hit) { tooltip.style.display = "none"; return; }
        const strut = hit.object.userData.struts[hit.instanceId!]; tooltip.style.display = "block"; tooltip.style.left = `${event.clientX - rect.left + 12}px`; tooltip.style.top = `${event.clientY - rect.top + 12}px`;
        tooltip.innerHTML = `<strong>Strut ${strut.id}</strong><span>${strut.classification}</span><small>Nodes ${strut.junction0} → ${strut.junction1}</small><small>Support ${(strut.support * 100).toFixed(1)}% · Gap ${strut.gap}</small><small>Nominal thickness ${strut.thickness ?? "n/a"} · Confidence ${(strut.confidence * 100).toFixed(0)}%</small>`;
      };
      renderer.domElement.addEventListener("pointermove", hover); renderer.domElement.addEventListener("pointerleave", () => { tooltip.style.display = "none"; });
      const select = (event: PointerEvent) => { const rect = renderer!.domElement.getBoundingClientRect(); pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1; pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1; raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObjects(scene.children, true).find(item => Array.isArray(item.object.userData.struts) && item.instanceId !== undefined); if (hit) { const strut = hit.object.userData.struts[hit.instanceId!]; onSelectStrut?.(strut); window.dispatchEvent(new CustomEvent("lattice-strut-selected", { detail: strut })); } };
      renderer.domElement.addEventListener("click", select);
      return () => { cancelAnimationFrame(initialLayoutFrame); resizeObserver.disconnect(); renderer?.domElement.removeEventListener("pointermove", hover); renderer?.domElement.removeEventListener("click", select); controls.dispose(); scene.traverse(object => { const mesh = object as import("three").Mesh; mesh.geometry?.dispose?.(); const material = mesh.material; if (Array.isArray(material)) material.forEach(item => item.dispose()); else material?.dispose?.(); }); };
    };
    let dispose: (() => void) | undefined; run().then(value => { dispose = value; }).catch(error => { if (canvasHost.current) canvasHost.current.textContent = error instanceof Error ? error.message : "WebGL viewer unavailable"; }); return () => { clean = true; slicePlane.current = null; sliceBounds.current = null; groups.current = {}; cancelAnimationFrame(frame); dispose?.(); renderer?.dispose(); renderer?.forceContextLoss(); };
  }, [runId]);
  return <div className="three-lattice" ref={mount} aria-label="Interactive 3D lattice viewer"><div className="three-canvas-host" ref={canvasHost}>Loading 3D geometry...</div></div>;
}
