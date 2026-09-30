"use client";

import { cn } from "@/lib/utils";

interface DomainTabsProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  tabs: { id: string; label: string; count?: number }[];
}

export function DomainTabs({ activeTab, onTabChange, tabs }: DomainTabsProps) {
  return (
    <div className="border-b border-brand-cream/10">
      <nav className="flex gap-1 overflow-x-auto pb-1" aria-label="Domain tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium rounded-lg transition-all whitespace-nowrap flex-shrink-0",
              activeTab === tab.id
                ? "bg-brand-amber/20 text-brand-amber border-b-2 border-brand-amber"
                : "text-brand-cream/60 hover:text-brand-cream hover:bg-brand-cream/5"
            )}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-brand-cream/10 text-brand-cream/70">
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </nav>
    </div>
  );
}