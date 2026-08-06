import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { default: "Inventory", template: "%s | NazmOS" },
  description: "Manage stock levels, filter by status, and reorder items before they stock out.",
  alternates: { canonical: "/inventory" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
