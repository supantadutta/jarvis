import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import TopBar from "@/components/TopBar";

export const metadata: Metadata = {
  title: "JARVIS — Cognitive Console",
  description: "Local-first multi-AI personal automation HUD",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <Nav />
          <div className="flex-1 flex flex-col min-w-0">
            <TopBar />
            <main className="flex-1 p-6 overflow-y-auto">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
