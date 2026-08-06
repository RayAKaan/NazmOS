import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Expiry Tracker",
  description: "Track batch expiry dates, manage FEFO rotation, and stay SFDA compliant.",
  alternates: { canonical: "/inventory/expiry" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
