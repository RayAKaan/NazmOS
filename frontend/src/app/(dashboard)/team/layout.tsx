import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Team",
  description: "Invite team members, manage roles, and control access to your NazmOS account.",
  alternates: { canonical: "/team" },
};

export default function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
