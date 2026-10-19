import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IncidentIQ", description: "AI-powered incident investigation workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
