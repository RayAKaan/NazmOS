import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Create account",
  description: "Create your NazmOS merchant account and get a free Money Audit for your store.",
  alternates: { canonical: "/register" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
