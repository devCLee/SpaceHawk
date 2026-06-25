import type { Metadata } from "next";
import { IBM_Plex_Sans_KR } from "next/font/google";
import "./globals.css";
import Header from "./Components/Header";
import Providers from "./providers";
import { t } from "@/lib/i18n/t";

// Korean-capable display/body font. IBM Plex Sans (Latin-only) has no Hangul, so
// Korean copy would fall back to a mismatched system font; the KR cut covers both
// scripts. preload:false — the Korean glyph range is large and should not block
// first paint.
const ibmPlexSansKR = IBM_Plex_Sans_KR({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: "SpaceHawk",
  description: t("meta.description"),
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
    <html lang="ko" suppressHydrationWarning>
      <body suppressHydrationWarning className={ibmPlexSansKR.className}>
        <Providers>
          <Header />
          {children}
        </Providers>
      </body>
    </html>
  );
}
