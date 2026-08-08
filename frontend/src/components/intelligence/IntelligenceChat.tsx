"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Sparkles, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { ReasoningPanel } from "./ReasoningPanel";
import { useIntelligenceChat } from "@/hooks/useIntelligenceChat";

interface IntelligenceChatProps {
  className?: string;
}

export function IntelligenceChat({ className }: IntelligenceChatProps) {
  const { messages, suggestions, isLoading, error, sendMessage } = useIntelligenceChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    sendMessage(input.trim());
    setInput("");
  };

  const handleSuggestion = (suggestion: string) => {
    if (isLoading) return;
    sendMessage(suggestion);
  };

  return (
    <div className={cn("flex flex-col h-full bg-bg-secondary border border-border rounded-2xl overflow-hidden", className)}>
      <div className="flex items-center gap-3 px-5 py-4 border-b border-border bg-bg-tertiary">
        <div className="w-8 h-8 rounded-lg bg-brand-teal/15 flex items-center justify-center text-brand-teal">
          <Sparkles className="w-4 h-4" />
        </div>
        <div>
          <h2 className="font-semibold text-sm">Nazm Copilot</h2>
          <p className="text-xs text-text-muted">Ask anything about your store</p>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="space-y-4">
            <div className="text-center py-8">
              <div className="w-12 h-12 rounded-xl bg-brand-teal/10 mx-auto flex items-center justify-center text-brand-teal mb-3">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="font-semibold text-text-primary">What would you like to know?</h3>
              <p className="text-sm text-text-muted mt-1">
                Nazm can reason across sales, inventory, context, and decisions.
              </p>
            </div>

            <div className="grid gap-2">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSuggestion(suggestion)}
                  className="text-left px-4 py-3 rounded-xl border border-border bg-bg-tertiary text-sm text-text-secondary hover:text-text-primary hover:border-brand-teal/30 hover:bg-brand-teal/5 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "flex",
              message.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            <div
              className={cn(
                "max-w-[90%] md:max-w-[80%] rounded-xl px-4 py-3 text-sm",
                message.role === "user"
                  ? "bg-brand-teal text-black rounded-br-none"
                  : "bg-bg-tertiary border border-border rounded-bl-none"
              )}
            >
              {message.role === "user" ? (
                <p>{message.content}</p>
              ) : message.reasoning ? (
                <ReasoningPanel response={message.reasoning} />
              ) : (
                <p>{message.content}</p>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-bg-tertiary border border-border rounded-xl rounded-bl-none px-4 py-3">
              <div className="flex items-center gap-2 text-text-muted text-sm">
                <Loader2 className="w-4 h-4 animate-spin text-brand-teal" />
                Nazm is thinking...
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-status-error/30 bg-status-error/10 p-3 text-sm text-status-error">
            {error}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-4 border-t border-border bg-bg-tertiary">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Nazm..."
            className="flex-1 rounded-xl border border-border bg-bg-primary px-4 py-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand-teal transition-colors"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-brand-teal text-black hover:bg-brand-teal-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="mt-2 text-[10px] text-text-muted text-center">
          AI-generated answers may be incorrect. Always review before acting.
        </p>
      </form>
    </div>
  );
}
