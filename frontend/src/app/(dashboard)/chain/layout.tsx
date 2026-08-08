import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chain Dashboard",
  description: "Chain-level revenue, transactions, and location performance for multi-branch retailers.",
  alternates: { canonical: "/chain" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
