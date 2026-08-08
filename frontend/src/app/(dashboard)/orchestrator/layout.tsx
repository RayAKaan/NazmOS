import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Orchestrator",
  description: "Multi-location stock rebalancing and proactive margin defense across branches.",
  alternates: { canonical: "/orchestrator" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
