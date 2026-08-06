import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to NazmOS to view your Money Audit, inventory alerts, and recovery actions.",
  alternates: { canonical: "/login" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
