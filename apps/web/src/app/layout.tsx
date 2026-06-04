import type { Metadata } from "next";
import "./globals.css";
import Header from "./Components/Header";
import Providers from "./providers";

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
    // suppressHydrationWarning: browser extensions (Grammarly, QuillBot, …)
    // inject attributes onto <html>/<body> before React hydrates, which would
    // otherwise log a hydration-mismatch warning. This only suppresses the
    // warning one level deep on these elements — it does not mask real
    // mismatches in app components.
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        style={{
          fontFamily:
            'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        }}
      >
        <Providers>
          <Header />
          {children}
        </Providers>
      </body>
    </html>
  );
}
