import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Upload",
  description: "Upload sales and inventory CSV or Excel files to power your NazmOS Money Audit.",
  alternates: { canonical: "/upload" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
