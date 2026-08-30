import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

export interface Supplier {
  id: string;
  name_ar: string;
  name_en: string;
  city: string;
  category: string;
  phone?: string;
  whatsapp_number?: string;
  lead_time_days: number;
  total_orders: number;
  total_volume_sar: number;
}

export function useSuppliers() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSuppliers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get("/suppliers");
      setSuppliers(response.data?.suppliers ?? []);
    } catch (err) {
      setError("Failed to load suppliers");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  return { suppliers, isLoading, error, refetch: fetchSuppliers };
}