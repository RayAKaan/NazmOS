import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Onboarding",
  description: "Set up your NazmOS store: create an admin account, upload your sales file, and open the dashboard.",
  alternates: { canonical: "/onboarding" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
