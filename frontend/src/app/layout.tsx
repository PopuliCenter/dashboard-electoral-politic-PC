import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Populi Electoral Dashboard",
  description:
    "Dashboard internal Populi Center untuk memetakan dan membandingkan hasil pemilu Jawa Barat 2019 dan 2024.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body className="min-h-screen bg-background">{children}</body>
    </html>
  );
}
