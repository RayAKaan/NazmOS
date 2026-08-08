import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import type { IntelligenceSummary } from "@/types/intelligence";

export function useIntelligenceSummary() {
  const { businessId } = useAppStore();
  const [summary, setSummary] = useState<IntelligenceSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!businessId) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.get<IntelligenceSummary>(
        `/dashboard/intelligence-summary?business_id=${businessId}`
      );
      setSummary(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load intelligence summary");
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { summary, isLoading, error, refetch: fetchSummary };
}
