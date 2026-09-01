import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { StructuredData } from "@/components/structured-data";
import { ServiceWorkerRegister } from "@/components/pwa/ServiceWorkerRegister";
import { WeaveSprite } from "@/components/ui/WeaveSprite";
import { ThemeScript } from "@/components/theme-script";

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://app.nazm.ai";

// Phase 1 typography: real display serif for headline money/KPI figures, self-hosted
// (committed woff2) so builds never depend on a Google Fonts fetch — see the font-stack
// note in build_design_tokens.ts. Exposed as --font-serif, consumed by the `font-serif`
// utility. Source Serif 4 ships lining+tabular figures by default, which is what keeps
// the animated tabular-nums money figures from jittering. Weights 200-900 (Black).
const serif = localFont({
  src: "./fonts/source-serif-4-latin.woff2",
  variable: "--font-serif",
  display: "swap",
  weight: "200 900",
});

// IBM Plex Sans Arabic — self-hosted woff2 (Arabic subset) for Arabic UI text, mirroring
// the Source Serif 4 pattern. Exposed as --font-arabic, consumed by the `font-arabic`
// utility and applied to the body whenever the document is RTL. Discrete weights, so each
// weight is a separate committed woff2. These files are NOT re-fetched at build time.
const arabic = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-arabic-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-arabic-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-arabic-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/ibm-plex-sans-arabic-700.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-arabic",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(appUrl),
  title: {
    default: "NazmOS — Inventory Intelligence OS by Nazmak",
    template: "%s | NazmOS",
  },
  description:
    "NazmOS is the inventory intelligence operating system for e-commerce and retail teams. Forecast demand, audit margins, orchestrate suppliers, and automate replenishment across every channel.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "NazmOS",
  },
  applicationName: "NazmOS",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "NazmOS",
  },
  twitter: {
    card: "summary_large_image",
    creator: "@nazmak_ai",
  },
  robots: {
    index: true,
    follow: true,
    "max-image-preview": "large",
  },
  icons: {
    icon: "/icon",
    apple: "/icon",
  },
  alternates: {
    canonical: "/",
  },
};

export const viewport: Viewport = {
  themeColor: "#14B8A6",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" className={`${serif.variable} ${arabic.variable}`} suppressHydrationWarning>
      <head>
        <StructuredData />
        <ThemeScript />
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var l=localStorage.getItem("nazmos-locale");if(l==="ar"){document.documentElement.dir="rtl";document.documentElement.lang="ar";document.documentElement.classList.add("arabic-font");}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-screen bg-background text-foreground font-sans antialiased">
        {/* §6: single shared WeaveTile sprite — referenced via <use> everywhere, never duplicated. */}
        <WeaveSprite />
        <Providers>
          {children}
          <ServiceWorkerRegister />
        </Providers>
      </body>
    </html>
  );
}
