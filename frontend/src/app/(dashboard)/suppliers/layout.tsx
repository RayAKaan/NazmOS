import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Suppliers",
  description: "View your supplier network, lead times, order volume, and contact details.",
  alternates: { canonical: "/suppliers" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
