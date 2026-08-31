"use client";

import { IntelligenceChat } from "@/components/intelligence/IntelligenceChat";
import { Sparkles } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="h-[calc(100vh-7rem)] md:h-[calc(100vh-6rem)] flex flex-col -mx-4 md:-mx-6 px-4 md:px-6 pb-4 md:pb-6">
      <div className="mb-4 shrink-0">
        <div className="flex items-center gap-2 text-brand-teal text-sm font-semibold">
          <Sparkles className="w-4 h-4" />
          <span>UNIFIED INTELLIGENCE API</span>
        </div>
        <h1 className="text-2xl md:text-3xl font-bold mt-1">Nazm Copilot</h1>
        <p className="text-muted-foreground text-sm">
          Reason across memory, graph, context, and decisions — all in one conversation.
        </p>
      </div>

      <IntelligenceChat className="flex-1 min-h-0" />
    </div>
  );
}
