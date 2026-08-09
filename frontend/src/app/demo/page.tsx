import type { Metadata } from "next";
import { permanentRedirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Demo",
  description: "See NazmOS in action with an interactive product demo and sample Money Audit.",
  alternates: { canonical: "/demo" },
};

export default function DemoRedirect() {
  permanentRedirect("/product-demo");
}
