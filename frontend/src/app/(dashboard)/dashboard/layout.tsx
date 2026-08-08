import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "Your NazmOS store overview with KPIs, sales trends, dead stock alerts, and quick actions.",
  alternates: { canonical: "/dashboard" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
