import type { Metadata } from "next";
import "./globals.css";
import Header from "./Components/Header";

export const metadata: Metadata = {
  title: "SpaceHawk",
  description:
    "SpaceHawk Space Environment & Threat Intelligence Operational Dashboard for Integrated Layered Operations",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        style={{
          fontFamily:
            'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        }}
      >
        <Header />
        {children}
      </body>
    </html>
  );
}
