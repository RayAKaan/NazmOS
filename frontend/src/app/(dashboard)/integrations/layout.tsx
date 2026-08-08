import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Integrations",
  description: "Connect your POS, e-commerce, or ERP systems to NazmOS for automatic data sync.",
  alternates: { canonical: "/integrations" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
