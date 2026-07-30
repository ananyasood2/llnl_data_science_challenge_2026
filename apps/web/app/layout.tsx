import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import "./globals.css";
import { WorkflowSidebar } from "./WorkflowSidebar";

export const metadata: Metadata = {
  title: "Lattice CT Inspection",
  description: "Scientific inspection workspace for lattice CT analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <main className="workspace">
          <Suspense fallback={null}>
            <WorkflowSidebar />
          </Suspense>
          {children}
        </main>
      </body>
    </html>
  );
}
