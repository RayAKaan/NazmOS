"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { 
  Link2, Plus, RefreshCw, Trash2, CheckCircle, 
  XCircle, Settings, Zap, Database, ShoppingCart
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";

interface POSConnection {
  id: string;
  adapter_type: string;
  connection_name: string;
  sync_status: string;
  sync_interval_minutes: number;
  sync_sales: boolean;
  sync_inventory: boolean;
  push_orders: boolean;
  last_sync_at: string;
  last_sync_records_processed: number;
  last_sync_error: string;
  is_active: boolean;
}

const ADAPTERS = [
  { id: "foodics", name: "Foodics POS (KSA)", icon: Zap, description: "Real-time OAuth & order created webhook sync" },
  { id: "salla", name: "Salla E-Commerce (KSA)", icon: ShoppingCart, description: "Sync Salla web orders into your retail recovery ledger" },
  { id: "tally", name: "Tally ERP", icon: Database, description: "Connect to Tally for real-time sync" },
  { id: "shopify", name: "Shopify", icon: ShoppingCart, description: "Sync with your Shopify store" },
  { id: "woocommerce", name: "WooCommerce", icon: ShoppingCart, description: "Connect WordPress WooCommerce" },
  { id: "zoho", name: "Zoho Inventory", icon: Database, description: "Sync with Zoho Inventory" },
  { id: "csv_webhook", name: "CSV/Webhook", icon: Zap, description: "Custom CSV import or webhook" },
];

const STATUS_COLORS: Record<string, string> = {
  synced: "text-green-400 bg-green-500/20",
  syncing: "text-blue-400 bg-blue-500/20",
  error: "text-red-400 bg-red-500/20",
  never_synced: "text-yellow-400 bg-yellow-500/20",
  disabled: "text-gray-400 bg-gray-500/20",
};

export default function IntegrationsPage() {
  const [connections, setConnections] = useState<POSConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedAdapter, setSelectedAdapter] = useState<string | null>(null);
  const { businessId } = useAppStore();

  const fetchConnections = useCallback(async () => {
    if (!businessId) return;
    try {
      const response = await api.get("/pos/connections", {
        params: { business_id: businessId },
      });
      setConnections(response.data);
    } catch (error) {
      console.error("Failed to fetch connections:", error);
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  const handleSync = async (connectionId: string) => {
    try {
      await api.post(`/pos/connections/${connectionId}/sync`, {}, {
        params: { business_id: businessId },
      });
      fetchConnections();
    } catch (error) {
      console.error("Failed to trigger sync:", error);
    }
  };

  const handleDelete = async (connectionId: string) => {
    if (!confirm("Are you sure you want to delete this connection?")) return;
    
    try {
      await api.delete(`/pos/connections/${connectionId}`, {
        params: { business_id: businessId },
      });
      fetchConnections();
    } catch (error) {
      console.error("Failed to delete connection:", error);
    }
  };

  const handleTestConnection = async (connectionId: string) => {
    try {
      const response = await api.post(`/pos/connections/${connectionId}/test`, {}, {
        params: { business_id: businessId },
      });
      alert(response.data.success ? "Connection successful!" : "Connection failed");
    } catch (error) {
      console.error("Failed to test connection:", error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 rounded-xl bg-accent-blue animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#f0f0f5]">Integrations</h1>
          <p className="text-sm text-[#8888a0]">
            Connect your POS systems and sync data automatically
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Integration
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[#1a1a2e] rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Link2 className="w-5 h-5 text-blue-400" />
            <span className="text-sm text-[#8888a0]">Active Connections</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {connections.filter((c) => c.is_active).length}
          </p>
        </div>
        <div className="bg-[#1a1a2e] rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <RefreshCw className="w-5 h-5 text-green-400" />
            <span className="text-sm text-[#8888a0]">Last Sync</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {connections[0]?.last_sync_at
              ? new Date(connections[0].last_sync_at).toLocaleTimeString()
              : "Never"}
          </p>
        </div>
        <div className="bg-[#1a1a2e] rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Zap className="w-5 h-5 text-purple-400" />
            <span className="text-sm text-[#8888a0]">Records Synced</span>
          </div>
          <p className="text-2xl font-bold text-[#f0f0f5]">
            {connections.reduce((sum, c) => sum + (c.last_sync_records_processed || 0), 0)}
          </p>
        </div>
      </div>

      <div className="bg-[#1a1a2e] rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-[#2a2a3e]">
          <h2 className="text-lg font-semibold text-[#f0f0f5]">Connected Systems</h2>
        </div>
        
        {connections.length === 0 ? (
          <div className="p-12 text-center">
            <Link2 className="w-16 h-16 text-[#555570] mx-auto mb-4" />
            <p className="text-[#8888a0] mb-4">No integrations configured yet</p>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors"
            >
              Add Your First Integration
            </button>
          </div>
        ) : (
          <div className="divide-y divide-[#2a2a3e]">
            {connections.map((conn) => {
              const adapter = ADAPTERS.find((a) => a.id === conn.adapter_type);
              const AdapterIcon = adapter?.icon || Link2;
              
              return (
                <div key={conn.id} className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-[#2a2a3e] flex items-center justify-center">
                      <AdapterIcon className="w-6 h-6 text-[#8888a0]" />
                    </div>
                    <div>
                      <p className="font-medium text-[#f0f0f5]">{conn.connection_name}</p>
                      <p className="text-sm text-[#8888a0]">{adapter?.name}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                      {conn.sync_status === "synced" ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : conn.sync_status === "error" ? (
                        <XCircle className="w-4 h-4 text-red-400" />
                      ) : null}
                      <span className={`px-2 py-1 rounded text-xs ${STATUS_COLORS[conn.sync_status]}`}>
                        {conn.sync_status.replace("_", " ")}
                      </span>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTestConnection(conn.id)}
                        className="p-2 text-[#8888a0] hover:bg-[#2a2a3e] rounded-lg transition-colors"
                        title="Test connection"
                      >
                        <Zap className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleSync(conn.id)}
                        disabled={conn.sync_status === "syncing"}
                        className="p-2 text-[#8888a0] hover:bg-[#2a2a3e] rounded-lg transition-colors disabled:opacity-50"
                        title="Sync now"
                      >
                        <RefreshCw className={`w-4 h-4 ${conn.sync_status === "syncing" ? "animate-spin" : ""}`} />
                      </button>
                      <button
                        onClick={() => handleDelete(conn.id)}
                        className="p-2 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-[#1a1a2e] rounded-2xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto"
          >
            <h3 className="text-lg font-semibold text-[#f0f0f5] mb-4">Add Integration</h3>
            
            {!selectedAdapter ? (
              <div className="grid grid-cols-2 gap-4">
                {ADAPTERS.map((adapter) => {
                  const Icon = adapter.icon;
                  return (
                    <button
                      key={adapter.id}
                      onClick={() => setSelectedAdapter(adapter.id)}
                      className="flex items-start gap-4 p-4 bg-[#2a2a3e] rounded-xl hover:bg-[#3a3a4e] transition-colors text-left"
                    >
                      <div className="w-10 h-10 rounded-lg bg-[#1a1a2e] flex items-center justify-center">
                        <Icon className="w-5 h-5 text-[#8888a0]" />
                      </div>
                      <div>
                        <p className="font-medium text-[#f0f0f5]">{adapter.name}</p>
                        <p className="text-sm text-[#8888a0]">{adapter.description}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div>
                <button
                  onClick={() => setSelectedAdapter(null)}
                  className="text-sm text-blue-400 mb-4"
                >
                  ← Back to integrations
                </button>
                
                <div className="space-y-4">
                  <p className="text-[#8888a0]">
                    Configure your {ADAPTERS.find((a) => a.id === selectedAdapter)?.name} connection.
                    This will open a setup wizard in the next step.
                  </p>
                  
                  <div className="bg-[#2a2a3e] rounded-xl p-4">
                    <h4 className="font-medium text-[#f0f0f5] mb-2">Coming Soon</h4>
                    <p className="text-sm text-[#8888a0]">
                      Full configuration UI for {selectedAdapter} is being built. 
                      Contact support to set up this integration.
                    </p>
                  </div>
                  
                  <button
                    onClick={() => setShowAddModal(false)}
                    className="w-full py-3 bg-[#2a2a3e] text-[#f0f0f5] rounded-xl hover:bg-[#3a3a4e] transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  );
}
