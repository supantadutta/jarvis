import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "JARVIS — Multi-AI Assistant",
  description: "Local-first multi-AI personal automation platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <Nav />
          <main className="flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
