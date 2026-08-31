import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { StructuredData } from "@/components/structured-data";
import { ServiceWorkerRegister } from "@/components/pwa/ServiceWorkerRegister";
import { WeaveSprite } from "@/components/ui/WeaveSprite";

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
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" className={`${serif.variable} dark`}>
      <head>
        <StructuredData />
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var l=localStorage.getItem("nazmos-locale");if(l==="ar"){document.documentElement.dir="rtl";document.documentElement.lang="ar";}}catch(e){}})();`,
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
