import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nazm Feed",
  description: "Review and approve AI-generated recovery actions ranked by confidence and value.",
  alternates: { canonical: "/feed" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
