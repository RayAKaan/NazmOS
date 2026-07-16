"use client";

import { ReactNode } from "react";
import { DemoProvider } from "@/lib/demo-engine";
import { DemoHeader } from "./DemoHeader";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";

export function DemoLayout({ children }: { children: ReactNode }) {
  return (
    <DemoProvider>
      <div className="min-h-screen bg-bg-primary">
        <DemoHeader />
        <div className="absolute top-14 right-4 z-50">
          <LanguageSwitcher variant="compact" />
        </div>
        {children}
      </div>
    </DemoProvider>
  );
}
