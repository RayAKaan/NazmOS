'use client';

import * as React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Filter, ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, Minus, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

type DecisionType = 'RESTOCK' | 'DISCOUNT' | 'PRICE_INCREASE' | 'ALERT' | 'REORDER';
type DecisionStatus = 'completed' | 'pending' | 'applied';

interface DecisionLog {
  id: string;
  type: DecisionType;
  status: DecisionStatus;
  product: string;
  quantity?: number;
  price?: number;
  reason: string;
  timestamp: string;
  savings?: number;
}

const MOCK_LOGS: DecisionLog[] = [
  { id: '1', type: 'RESTOCK', status: 'applied', product: 'Almarai Fresh Milk 1L 500ml', quantity: 135, reason: 'Stockout predicted in 2 days', timestamp: '2 min ago', savings: 4500 },
  { id: '2', type: 'DISCOUNT', status: 'applied', product: 'Parle-G Biscuits', price: 5, reason: 'Expiring in 3 days, velocity low', timestamp: '15 min ago', savings: 120 },
  { id: '3', type: 'ALERT', status: 'completed', product: 'Maggi Noodles', quantity: 50, reason: 'Unusual demand spike detected', timestamp: '1 hour ago' },
  { id: '4', type: 'PRICE_INCREASE', status: 'pending', product: 'Tata Salt 1kg', price: 3, reason: 'Competitor price increase', timestamp: '2 hours ago' },
  { id: '5', type: 'REORDER', status: 'applied', product: 'Colgate Max Fresh', quantity: 24, reason: 'Below reorder point (50 units)', timestamp: '3 hours ago', savings: 2800 },
  { id: '6', type: 'RESTOCK', status: 'applied', product: 'Fortune Oil 1L', quantity: 48, reason: 'Weekly replenishment', timestamp: '5 hours ago', savings: 3200 },
];

const TYPE_CONFIG: Record<DecisionType, { label: string; icon: React.ReactNode; color: string }> = {
  RESTOCK: { label: 'Restock', icon: <ArrowUpRight className="w-3 h-3" />, color: 'bg-status-info/20 text-status-info border-status-info/30' },
  DISCOUNT: { label: 'Discount', icon: <ArrowDownRight className="w-3 h-3" />, color: 'bg-status-warning/20 text-status-warning border-status-warning/30' },
  PRICE_INCREASE: { label: 'Price Up', icon: <ArrowUpRight className="w-3 h-3" />, color: 'bg-status-success/20 text-status-success border-status-success/30' },
  ALERT: { label: 'Alert', icon: <Minus className="w-3 h-3" />, color: 'bg-status-error/20 text-status-error border-status-error/30' },
  REORDER: { label: 'Reorder', icon: <ArrowUpRight className="w-3 h-3" />, color: 'bg-accent-primary/20 text-accent-primary border-accent-primary/30' },
};

const STATUS_CONFIG: Record<DecisionStatus, { label: string; color: string }> = {
  completed: { label: 'Completed', color: 'text-status-success' },
  pending: { label: 'Pending', color: 'text-status-warning' },
  applied: { label: 'Applied', color: 'text-status-info' },
};

export function DecisionLogTable() {
  const [search, setSearch] = React.useState('');
  const [filterType, setFilterType] = React.useState<DecisionType | 'all'>('all');
  const [expandedId, setExpandedId] = React.useState<string | null>(null);

  const filteredLogs = MOCK_LOGS.filter(log => {
    const matchesSearch = log.product.toLowerCase().includes(search.toLowerCase()) ||
                          log.reason.toLowerCase().includes(search.toLowerCase());
    const matchesType = filterType === 'all' || log.type === filterType;
    return matchesSearch && matchesType;
  });

  return (
    <div className="bg-bg-secondary border border-border-primary">
      <div className="p-4 border-b border-border-primary flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search products or reasons..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-bg-tertiary border border-border-primary text-text-primary placeholder:text-text-muted font-sans text-sm focus:outline-none focus:border-accent-primary transition-colors"
          />
        </div>
        
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-text-muted" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as DecisionType | 'all')}
            className="px-3 py-2 bg-bg-tertiary border border-border-primary text-text-primary font-sans text-sm focus:outline-none focus:border-accent-primary cursor-pointer"
          >
            <option value="all">All Types</option>
            {Object.entries(TYPE_CONFIG).map(([key, config]) => (
              <option key={key} value={key}>{config.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border-primary">
              <th className="px-4 py-3 text-left font-sans text-xs text-text-muted uppercase tracking-wider">Type</th>
              <th className="px-4 py-3 text-left font-sans text-xs text-text-muted uppercase tracking-wider">Product</th>
              <th className="px-4 py-3 text-left font-sans text-xs text-text-muted uppercase tracking-wider hidden md:table-cell">Details</th>
              <th className="px-4 py-3 text-left font-sans text-xs text-text-muted uppercase tracking-wider hidden sm:table-cell">Time</th>
              <th className="px-4 py-3 text-left font-sans text-xs text-text-muted uppercase tracking-wider">Status</th>
              <th className="px-4 py-3 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {filteredLogs.map((log) => (
              <React.Fragment key={log.id}>
                <tr 
                  className={cn(
                    'border-b border-border-primary transition-colors cursor-pointer',
                    expandedId === log.id ? 'bg-bg-tertiary' : 'hover:bg-bg-tertiary/50'
                  )}
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                >
                  <td className="px-4 py-3">
                    <span className={cn('inline-flex items-center gap-1.5 px-2 py-1 border text-xs font-mono', TYPE_CONFIG[log.type].color)}>
                      {TYPE_CONFIG[log.type].icon}
                      {TYPE_CONFIG[log.type].label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-sans text-sm text-text-primary">{log.product}</span>
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <span className="font-sans text-sm text-text-secondary truncate max-w-[200px] block">
                      {log.quantity && `${log.quantity} units`}
                      {log.price && `${log.price > 0 ? '+' : ''}﷼ ${Math.abs(log.price)}`}
                      {log.savings && `• Save ﷼ ${log.savings}`}
                    </span>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <span className="font-sans text-sm text-text-muted flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {log.timestamp}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn('font-sans text-sm', STATUS_CONFIG[log.status].color)}>
                      {STATUS_CONFIG[log.status].label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {expandedId === log.id ? (
                      <ChevronUp className="w-4 h-4 text-text-muted" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-text-muted" />
                    )}
                  </td>
                </tr>
                
                <AnimatePresence>
                  {expandedId === log.id && (
                    <motion.tr
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <td colSpan={6} className="px-4 py-4 bg-bg-tertiary border-b border-border-primary">
                        <div className="space-y-3">
                          <div>
                            <span className="font-sans text-xs text-text-muted uppercase tracking-wider">Reason</span>
                            <p className="font-sans text-sm text-text-primary mt-1">{log.reason}</p>
                          </div>
                          
                          {log.savings && (
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-1 bg-status-success/20 text-status-success text-xs font-mono">
                                +﷼ {log.savings} savings
                              </span>
                            </div>
                          )}
                          
                          <div className="flex gap-2 pt-2">
                            <button className="px-3 py-1.5 bg-accent-primary text-bg-primary text-xs font-sans font-medium hover:bg-accent-primary/90 transition-colors">
                              {log.status === 'pending' ? 'Apply Now' : 'View Details'}
                            </button>
                            <button className="px-3 py-1.5 bg-bg-secondary text-text-secondary text-xs font-sans border border-border-primary hover:text-text-primary hover:bg-bg-tertiary transition-colors">
                              Dismiss
                            </button>
                          </div>
                        </div>
                      </td>
                    </motion.tr>
                  )}
                </AnimatePresence>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {filteredLogs.length === 0 && (
        <div className="p-12 text-center">
          <p className="font-sans text-text-muted">No decisions found matching your criteria.</p>
        </div>
      )}
    </div>
  );
}
