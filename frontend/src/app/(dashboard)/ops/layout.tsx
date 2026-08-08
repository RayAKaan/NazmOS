import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pilot Console",
  description: "Founder pilot console for uploads, Money Audit queue, recovery actions, and issue tracking.",
  alternates: { canonical: "/ops" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
