import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { InventoryResponse, ItemDetail } from "@/types/inventory";

export function useInventory() {
  const { businessId } = useAppStore();
  const [inventory, setInventory] = useState<InventoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState({
    status: "all",
    category: "all",
    search: "",
    sort: "days_left",
    order: "asc" as "asc" | "desc",
    page: 1,
    limit: 20,
  });

  const fetchInventory = useCallback(async () => {
    if (!businessId) return;

    setIsLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        business_id: businessId,
        status: filters.status,
        category: filters.category,
        search: filters.search,
        sort: filters.sort,
        order: filters.order,
        page: filters.page.toString(),
        limit: filters.limit.toString(),
      });

      const response = await api.get(`/inventory?${params}`);
      setInventory(response.data);
    } catch (err) {
      setError("Failed to load inventory");
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [businessId, filters]);

  useEffect(() => {
    fetchInventory();
  }, [fetchInventory]);

  const getItemDetail = async (itemId: string): Promise<ItemDetail | null> => {
    if (!businessId) return null;

    try {
      const response = await api.get(`/inventory/${itemId}/detail?business_id=${businessId}`);
      return response.data;
    } catch (err) {
      console.error(err);
      return null;
    }
  };

  const updateFilters = (newFilters: Partial<typeof filters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters, page: 1 }));
  };

  const setPage = (page: number) => {
    setFilters((prev) => ({ ...prev, page }));
  };

  return {
    inventory,
    isLoading,
    error,
    filters,
    updateFilters,
    setPage,
    getItemDetail,
    refetch: fetchInventory,
  };
}
