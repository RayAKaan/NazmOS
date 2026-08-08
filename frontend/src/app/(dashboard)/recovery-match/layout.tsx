import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Recovery Match",
  description: "Turn healthy surplus stock into recovered cash by matching with nearby opted-in stores.",
  alternates: { canonical: "/recovery-match" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
