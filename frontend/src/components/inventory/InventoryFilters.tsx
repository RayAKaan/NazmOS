"use client";

import { Search, Filter } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { useState, useEffect } from "react";

interface InventoryFiltersProps {
  onSearch: (value: string) => void;
  onStatusChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  searchValue: string;
  statusValue: string;
  categoryValue: string;
  categories: string[];
}

export function InventoryFilters({
  onSearch,
  onStatusChange,
  onCategoryChange,
  searchValue,
  statusValue,
  categoryValue,
  categories,
}: InventoryFiltersProps) {
  const [localSearch, setLocalSearch] = useState(searchValue);

  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(localSearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, onSearch]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search items..."
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-surface border border-border rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue transition-colors"
          />
        </div>
      </div>

      <div className="flex items-center gap-3 overflow-x-auto pb-1 -mx-4 px-4 md:mx-0 md:px-0">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-text-muted" />
          <span className="text-sm text-text-muted">Filters:</span>
        </div>

        <select
          value={statusValue}
          onChange={(e) => onStatusChange(e.target.value)}
          className="px-3 py-1.5 bg-surface border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue cursor-pointer"
        >
          <option value="all">All Status</option>
          <option value="critical">Critical</option>
          <option value="low">Low</option>
          <option value="healthy">Healthy</option>
          <option value="overstock">Overstock</option>
          <option value="dead">Dead</option>
        </select>

        <select
          value={categoryValue}
          onChange={(e) => onCategoryChange(e.target.value)}
          className="px-3 py-1.5 bg-surface border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent-blue cursor-pointer"
        >
          <option value="all">All Categories</option>
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
