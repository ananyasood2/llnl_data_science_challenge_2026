import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import "./viewer-overrides.css";

export const metadata: Metadata = {
  title: "Lattice CT Inspection",
  description: "Scientific inspection workspace for lattice CT analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
