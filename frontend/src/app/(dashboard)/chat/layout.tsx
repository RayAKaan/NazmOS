import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nazm Copilot",
  description: "Ask Nazm anything about your store. Reason across sales, inventory, context, and decisions.",
  alternates: { canonical: "/chat" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
