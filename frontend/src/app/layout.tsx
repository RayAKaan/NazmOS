import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { StructuredData } from "@/components/structured-data";
import { RegisterServiceWorker } from "@/components/RegisterServiceWorker";

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://app.nazm.ai";

export const viewport: Viewport = {
  themeColor: "#6366f1",
};

export const metadata: Metadata = {
  metadataBase: new URL(appUrl),
  title: {
    default: "NazmOS — Inventory Intelligence OS by Nazmak",
    template: "%s | NazmOS",
  },
  manifest: "/manifest.json",
  description:
    "NazmOS is the inventory intelligence operating system for e-commerce and retail teams. Forecast demand, audit margins, orchestrate suppliers, and automate replenishment across every channel.",
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
    icon: "/icon.png",
    shortcut: "/favicon.ico",
    apple: "/icon.png",
  },
  alternates: {
    canonical: "/",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr">
      <head>
        <StructuredData />
      </head>
      <body className="min-h-screen bg-bg-primary text-text-primary font-sans antialiased">
        <RegisterServiceWorker />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
