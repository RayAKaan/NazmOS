"use client";

import { useState } from "react";
import { Package } from "lucide-react";
import { InventoryFilters } from "@/components/inventory/InventoryFilters";
import { InventoryTable } from "@/components/inventory/InventoryTable";
import { ReorderModal } from "@/components/inventory/ReorderModal";
import { useInventory } from "@/hooks/useInventory";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { formatCurrency } from "@/lib/utils";

export default function InventoryPage() {
  const { inventory, isLoading, filters, updateFilters, setPage, getItemDetail } = useInventory();
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleItemClick = async (itemId: string) => {
    const detail = await getItemDetail(itemId);
    if (detail) {
      setSelectedItem(detail);
      setIsModalOpen(true);
    }
  };

  const categories = (inventory?.items
    .map((item) => item.category)
    .filter((cat, idx, arr) => cat && arr.indexOf(cat) === idx) || []) as string[];

  return (
    <div className="space-y-6 animate-in">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold flex items-center gap-3">
          <Package className="w-8 h-8" />
          Inventory
        </h1>
        <p className="text-text-muted">Manage your stock levels</p>
      </div>

      {inventory && (
        <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0">
          <Badge variant="default" className="px-4 py-2">
            All: {inventory.summary.total_items}
          </Badge>
          <Badge variant="danger" className="px-4 py-2">
            Critical: {inventory.summary.critical_count}
          </Badge>
          <Badge variant="warning" className="px-4 py-2">
            Low: {inventory.summary.low_count}
          </Badge>
          <Badge variant="success" className="px-4 py-2">
            Healthy: {inventory.summary.healthy_count}
          </Badge>
          <Badge variant="purple" className="px-4 py-2">
            Overstock: {inventory.summary.overstock_count}
          </Badge>
        </div>
      )}

      <div className="p-5 rounded-xl bg-surface border border-border">
        <InventoryFilters
          searchValue={filters.search}
          statusValue={filters.status}
          categoryValue={filters.category}
          onSearch={(value) => updateFilters({ search: value })}
          onStatusChange={(value) => updateFilters({ status: value })}
          onCategoryChange={(value) => updateFilters({ category: value })}
          categories={categories}
        />
      </div>

      <div className="p-5 rounded-xl bg-surface border border-border">
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : (
          <InventoryTable
            data={inventory}
            isLoading={isLoading}
            onItemClick={handleItemClick}
          />
        )}

        {inventory && inventory.pagination.total_pages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
            <p className="text-sm text-text-muted">
              Page {inventory.pagination.page} of {inventory.pagination.total_pages}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(inventory.pagination.page - 1)}
                disabled={inventory.pagination.page === 1}
                className="px-4 py-2 bg-surface-hover rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(inventory.pagination.page + 1)}
                disabled={inventory.pagination.page === inventory.pagination.total_pages}
                className="px-4 py-2 bg-surface-hover rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {inventory && (
        <div className="p-5 rounded-xl bg-surface border border-border">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-text-muted">Total Stock Value</p>
              <p className="text-xl font-bold">{formatCurrency(inventory.summary.total_stock_value)}</p>
            </div>
            <div>
              <p className="text-sm text-text-muted">Items Needing Attention</p>
              <p className="text-xl font-bold text-accent-yellow">
                {inventory.summary.critical_count + inventory.summary.low_count}
              </p>
            </div>
          </div>
        </div>
      )}

      <ReorderModal
        item={selectedItem}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedItem(null);
        }}
      />
    </div>
  );
}
