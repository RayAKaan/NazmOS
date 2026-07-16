"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { 
  Building2, MapPin, TrendingUp, TrendingDown, AlertTriangle,
  ChevronRight, DollarSign, ShoppingCart, Users
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

interface LocationSummary {
  id: string;
  name: string;
  city: string;
  type: string;
  status: string;
  revenue_today: number;
  transactions_today: number;
}

interface ChainDashboard {
  organization_id: string;
  organization_name: string;
  total_locations: number;
  total_revenue_today: number;
  total_revenue_yesterday: number;
  total_transactions_today: number;
  locations_summary: LocationSummary[];
}

const formatSAR = (amount: number) => {
  return new Intl.NumberFormat("ar-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0,
  }).format(amount);
};

export default function ChainDashboardPage() {
  const [dashboard, setDashboard] = useState<ChainDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const { businessId } = useAppStore();

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const response = await api.get("/organizations/chain/dashboard", {
          params: { business_id: businessId },
        });
        setDashboard(response.data);
      } catch (error) {
        console.error("Failed to fetch chain dashboard:", error);
      } finally {
        setLoading(false);
      }
    };

    if (businessId) {
      fetchDashboard();
    }
  }, [businessId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 rounded-xl bg-accent-blue animate-pulse" />
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="text-center py-12">
        <Building2 className="w-16 h-16 text-[#8888a0] mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-[#f0f0f5] mb-2">
          Chain Dashboard
        </h2>
        <p className="text-[#8888a0]">
          Create or join an organization to see chain-level insights.
        </p>
      </div>
    );
  }

  const revenueChange = dashboard.total_revenue_yesterday > 0
    ? ((dashboard.total_revenue_today - dashboard.total_revenue_yesterday) / dashboard.total_revenue_yesterday) * 100
    : 0;

  const criticalLocations = dashboard.locations_summary.filter(
    (loc) => loc.revenue_today < 5000
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f0f5]">
            {dashboard.organization_name}
          </h1>
          <p className="text-sm text-[#8888a0]">
            {dashboard.total_locations} locations across India
          </p>
        </div>
        <Link
          href="/organizations/settings"
          className="px-4 py-2 bg-[#1a1a2e] text-[#f0f0f5] rounded-xl hover:bg-[#2a2a3e] transition-colors"
        >
          Settings
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#1a1a2e] rounded-2xl p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-green-500/20 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-green-400" />
            </div>
            <span className="text-sm text-[#8888a0]">Today's Revenue</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {formatSAR(dashboard.total_revenue_today)}
          </p>
          <div className="flex items-center gap-1 mt-2">
            {revenueChange >= 0 ? (
              <TrendingUp className="w-4 h-4 text-green-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-red-400" />
            )}
            <span className={`text-sm ${revenueChange >= 0 ? "text-green-400" : "text-red-400"}`}>
              {Math.abs(revenueChange).toFixed(1)}%
            </span>
            <span className="text-sm text-[#8888a0]">vs yesterday</span>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-[#1a1a2e] rounded-2xl p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center">
              <ShoppingCart className="w-5 h-5 text-blue-400" />
            </div>
            <span className="text-sm text-[#8888a0]">Transactions</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {dashboard.total_transactions_today.toLocaleString("ar-SA")}
          </p>
          <p className="text-sm text-[#8888a0] mt-2">Today</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-[#1a1a2e] rounded-2xl p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-purple-400" />
            </div>
            <span className="text-sm text-[#8888a0]">Locations</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {dashboard.total_locations}
          </p>
          <p className="text-sm text-[#8888a0] mt-2">Active</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-[#1a1a2e] rounded-2xl p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-red-400" />
            </div>
            <span className="text-sm text-[#8888a0]">Alerts</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {criticalLocations.length}
          </p>
          <p className="text-sm text-red-400 mt-2">Need attention</p>
        </motion.div>
      </div>

      {criticalLocations.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-red-500/10 border border-red-500/30 rounded-2xl p-4"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="text-red-400 font-medium">
              {criticalLocations.length} location(s) performing below target
            </span>
          </div>
        </motion.div>
      )}

      <div className="bg-[#1a1a2e] rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-[#2a2a3e]">
          <h2 className="text-lg font-semibold text-[#f0f0f5]">All Locations</h2>
        </div>
        
        <div className="divide-y divide-[#2a2a3e]">
          {dashboard.locations_summary.map((location) => (
            <Link
              key={location.id}
              href={`/chain/${location.id}`}
              className="flex items-center justify-between p-4 hover:bg-[#1e1e2e] transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-[#2a2a3e] flex items-center justify-center">
                  <MapPin className="w-5 h-5 text-[#8888a0]" />
                </div>
                <div>
                  <p className="font-medium text-[#f0f0f5]">{location.name}</p>
                  <p className="text-sm text-[#8888a0]">{location.city}</p>
                </div>
              </div>
              
              <div className="flex items-center gap-6">
                <div className="text-right">
                  <p className="font-medium text-[#f0f0f5]">
                    {formatSAR(location.revenue_today)}
                  </p>
                  <p className="text-sm text-[#8888a0]">
                    {location.transactions_today} transactions
                  </p>
                </div>
                <ChevronRight className="w-5 h-5 text-[#555570]" />
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
