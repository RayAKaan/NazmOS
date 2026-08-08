import { useState, useCallback, useEffect } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { IntelligenceReasonResponse, ChatSuggestion } from "@/types/intelligence";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content?: string;
  reasoning?: IntelligenceReasonResponse;
  createdAt: string;
}

export function useIntelligenceChat() {
  const { businessId } = useAppStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSuggestions = useCallback(async () => {
    if (!businessId) return;
    try {
      const res = await api.get<ChatSuggestion>(`/chat/suggestions?business_id=${businessId}`);
      setSuggestions(res.data.suggestions || []);
    } catch {
      setSuggestions([
        "What should I order urgently right now?",
        "Why do Wednesday sales always dip by 31%?",
        "What's my stock value tied up in dead items?",
        "Forecast my weekend sales this Saturday and Sunday",
      ]);
    }
  }, [businessId]);

  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  const sendMessage = useCallback(
    async (question: string) => {
      if (!businessId || !question.trim()) return;

      const userMessage: ChatMessage = {
        id: `${Date.now()}-user`,
        role: "user",
        content: question.trim(),
        createdAt: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await api.post<IntelligenceReasonResponse>(
          `/chat/reason?business_id=${businessId}`,
          { message: question.trim(), context: {} }
        );

        const assistantMessage: ChatMessage = {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          reasoning: res.data,
          createdAt: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err: any) {
        setError(err?.response?.data?.detail || "Nazm could not answer that. Try rephrasing your question.");
      } finally {
        setIsLoading(false);
      }
    },
    [businessId]
  );

  return {
    messages,
    suggestions,
    isLoading,
    error,
    sendMessage,
    loadSuggestions,
  };
}
