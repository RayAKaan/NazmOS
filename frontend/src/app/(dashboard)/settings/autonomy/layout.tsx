import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Autonomy Settings",
  description: "Adjust how much NazmOS can act on its own across restocking, pricing, and expiry alerts.",
  alternates: { canonical: "/settings/autonomy" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
