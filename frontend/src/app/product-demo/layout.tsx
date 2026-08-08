import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Interactive Demo",
  description: "Run a Retail Recovery Simulation for baqala, date shop, cafe, pharmacy, or supermarket.",
  alternates: { canonical: "/product-demo" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
