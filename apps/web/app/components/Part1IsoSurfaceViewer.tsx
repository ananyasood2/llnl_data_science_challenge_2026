"use client";

import { useEffect, useRef } from "react";

export default function Part1IsoSurfaceViewer({ refreshKey }: { refreshKey?: string }) {
  const mount = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let disposed = false;
    let frame = 0;
    let renderer: import("three").WebGLRenderer | undefined;
    const run = async () => {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      const response = await fetch(`${process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://127.0.0.1:8001"}/api/v1/part1/mesh`, { cache: "no-store" });
      if (!response.ok) throw new Error(`Live 3D data unavailable (${response.status})`);
      const data = await response.json() as { vertices: number[][]; faces: number[][]; skeleton: number[][] };
      if (disposed || !mount.current) return;
      const scene = new THREE.Scene(); scene.background = new THREE.Color("#f7faf8");
      const camera = new THREE.PerspectiveCamera(38, 1, .1, 500); camera.position.set(82, 64, 92);
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" }); renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); mount.current.replaceChildren(renderer.domElement);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x35534c, 2.3)); const key = new THREE.DirectionalLight(0xffffff, 2.8); key.position.set(55, 75, 45); scene.add(key);
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.Float32BufferAttribute(data.vertices.flat(), 3)); geometry.setIndex(data.faces.flat()); geometry.computeVertexNormals();
      const surface = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: "#4ab39b", transparent: true, opacity: .43, roughness: .5, side: THREE.DoubleSide, depthWrite: false })); scene.add(surface);
      const skeletonGeometry = new THREE.BufferGeometry(); skeletonGeometry.setAttribute("position", new THREE.Float32BufferAttribute(data.skeleton.flat(), 3)); const skeleton = new THREE.Points(skeletonGeometry, new THREE.PointsMaterial({ color: "#e99027", size: .7, sizeAttenuation: true })); scene.add(skeleton);
      const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true; controls.target.set(0, 0, 0); controls.minDistance = 45; controls.maxDistance = 220; controls.update();
      const resize = () => { if (!renderer || !mount.current) return; const rect = mount.current.getBoundingClientRect(); if (!rect.width || !rect.height) return; camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix(); renderer.setSize(rect.width, rect.height, false); };
      const observer = new ResizeObserver(resize); observer.observe(mount.current); resize(); const animate = () => { frame = requestAnimationFrame(animate); controls.update(); renderer?.render(scene, camera); }; animate();
      return () => { observer.disconnect(); controls.dispose(); geometry.dispose(); skeletonGeometry.dispose(); (surface.material as import("three").Material).dispose(); (skeleton.material as import("three").Material).dispose(); };
    };
    let cleanup: (() => void) | undefined;
    run().then(value => { cleanup = value; }).catch(error => { if (mount.current) mount.current.textContent = error instanceof Error ? error.message : "Live 3D view unavailable"; });
    return () => { disposed = true; cancelAnimationFrame(frame); cleanup?.(); renderer?.dispose(); renderer?.forceContextLoss(); };
  }, [refreshKey]);

  return <div className="part1-live-3d" ref={mount}>Loading live isosurface…</div>;
}
