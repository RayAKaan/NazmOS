import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Money Audit",
  description: "See cash trapped in your store: dead stock, stockout risk, margin leakage, and recovery actions.",
  alternates: { canonical: "/money-audit" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
