"use client";

import { useEffect, useRef, useState } from "react";

type StructureViewerFrameProps = {
  viewerUrl: string;
};

export function StructureViewerFrame({ viewerUrl }: StructureViewerFrameProps) {
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [viewportLabel, setViewportLabel] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setState((current) => (current === "loading" ? "unavailable" : current));
    }, 6500);

    return () => window.clearTimeout(timeout);
  }, [viewerUrl]);

  useEffect(() => {
    const viewerOrigin = new URL(viewerUrl, window.location.href).origin;
    const onMessage = (event: MessageEvent) => {
      if (
        event.origin !== viewerOrigin ||
        event.source !== frameRef.current?.contentWindow ||
        !event.data ||
        event.data.type !== "lattice.viewport.v1"
      ) {
        return;
      }
      const context = event.data.context;
      if (!context || context.version !== "1") {
        return;
      }
      setViewportLabel(
        `${context.dataset_id} · revision ${context.viewer_revision} · ` +
          `bounds ${context.region?.min_xyz?.join(", ")} → ${context.region?.max_xyz?.join(", ")}`,
      );
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [viewerUrl]);

  return (
    <section className="structure-viewer" aria-label="3D validation dashboard">
      {state === "loading" ? (
        <div className="viewer-status" role="status">
          Loading 3D validation dashboard...
        </div>
      ) : null}
      {state === "unavailable" ? (
        <div className="viewer-status viewer-status-error" role="alert">
          The Dash structure viewer is not responding at {viewerUrl}. Start it with{" "}
          <code>npm run dev:structure</code>, then refresh this page.
        </div>
      ) : null}
      <iframe
        ref={frameRef}
        title="3D structure validation dashboard"
        src={viewerUrl}
        className="structure-iframe"
        onLoad={() => setState("ready")}
      />
      {viewportLabel ? (
        <p className="viewer-viewport-context" role="status">
          Copilot viewport: {viewportLabel}
        </p>
      ) : null}
    </section>
  );
}
