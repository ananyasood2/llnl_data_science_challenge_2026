"use client";

import { useEffect, useState } from "react";

type StructureViewerFrameProps = {
  viewerUrl: string;
};

export function StructureViewerFrame({ viewerUrl }: StructureViewerFrameProps) {
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setState((current) => (current === "loading" ? "unavailable" : current));
    }, 6500);

    return () => window.clearTimeout(timeout);
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
        title="3D structure validation dashboard"
        src={viewerUrl}
        className="structure-iframe"
        onLoad={() => setState("ready")}
      />
    </section>
  );
}
