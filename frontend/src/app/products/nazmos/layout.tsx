import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "NazmOS — The Operating System for Business Decisions",
  description:
    "NazmOS is Nazmak's operating system: it connects your fragmented business data, builds a live knowledge graph and business memory, and reasons toward decisions you approve before anything happens.",
  alternates: {
    canonical: "/products/nazmos",
  },
};

export default function NazmosLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
