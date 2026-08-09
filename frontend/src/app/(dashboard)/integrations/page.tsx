"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Link2, Plus, RefreshCw, Trash2, CheckCircle, 
  XCircle, Zap, Database, ShoppingCart, Store, Building2, ArrowLeft
} from "lucide-react";
import api from "@/lib/api";
import { useAppStore } from "@/stores/appStore";
import { cn } from "@/lib/utils";

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

type AdapterId = "foodics" | "salla" | "zid" | "qoyod" | "shopify" | "woocommerce" | "tally" | "zoho" | "csv_webhook";

interface AdapterConfig {
  id: AdapterId;
  name: string;
  icon: React.ElementType;
  description: string;
  category: "Saudi-native" | "Global" | "Custom";
  fields: { key: string; label: string; type?: string; placeholder?: string; required?: boolean }[];
}

const ADAPTERS: AdapterConfig[] = [
  { 
    id: "foodics", 
    name: "Foodics POS", 
    icon: Store, 
    description: "F&B POS webhooks and API sync for Saudi restaurants.",
    category: "Saudi-native",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Foodics branch", required: true },
      { key: "access_token", label: "Foodics API token (optional)", placeholder: "For product/order fetch", type: "password" },
      { key: "webhook_secret", label: "Webhook secret", placeholder: "For real-time order webhooks", type: "password" },
    ]
  },
  { 
    id: "salla", 
    name: "Salla E-Commerce", 
    icon: ShoppingCart, 
    description: "Sync Salla web orders and products into NazmOS.",
    category: "Saudi-native",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Salla store", required: true },
      { key: "access_token", label: "Salla access token", placeholder: "From Salla app settings", type: "password", required: true },
      { key: "webhook_secret", label: "Webhook secret (optional)", placeholder: "For real-time order webhooks", type: "password" },
    ]
  },
  { 
    id: "zid", 
    name: "Zid E-Commerce", 
    icon: ShoppingCart, 
    description: "Sync Zid orders and inventory into your retail recovery ledger.",
    category: "Saudi-native",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Zid store", required: true },
      { key: "access_token", label: "Zid API token", placeholder: "From Zid merchant settings", type: "password", required: true },
    ]
  },
  { 
    id: "qoyod", 
    name: "Qoyod Accounting", 
    icon: Building2, 
    description: "Pull products and sales invoices from Qoyod (read-only).",
    category: "Saudi-native",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Qoyod account", required: true },
      { key: "api_key", label: "Qoyod API key", placeholder: "From Qoyod integrations", type: "password", required: true },
    ]
  },
  { 
    id: "shopify", 
    name: "Shopify", 
    icon: ShoppingCart, 
    description: "Sync with your Shopify store.",
    category: "Global",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Shopify store", required: true },
      { key: "shop_name", label: "Shop name", placeholder: "your-store", required: true },
      { key: "access_token", label: "Access token", type: "password", required: true },
    ]
  },
  { 
    id: "woocommerce", 
    name: "WooCommerce", 
    icon: ShoppingCart, 
    description: "Connect WordPress WooCommerce.",
    category: "Global",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My WooCommerce store", required: true },
      { key: "site_url", label: "Site URL", placeholder: "https://your-store.com", required: true },
      { key: "consumer_key", label: "Consumer key", required: true },
      { key: "consumer_secret", label: "Consumer secret", type: "password", required: true },
    ]
  },
  { 
    id: "tally", 
    name: "Tally ERP", 
    icon: Database, 
    description: "Connect to Tally for real-time sync.",
    category: "Global",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "My Tally server", required: true },
      { key: "tally_url", label: "Tally URL", placeholder: "http://localhost:9000", required: true },
      { key: "company_name", label: "Company name", required: true },
    ]
  },
  { 
    id: "csv_webhook", 
    name: "CSV / Webhook", 
    icon: Zap, 
    description: "Custom CSV import or webhook endpoint.",
    category: "Custom",
    fields: [
      { key: "connection_name", label: "Connection name", placeholder: "Custom bridge", required: true },
      { key: "endpoint_url", label: "Endpoint URL", placeholder: "https://..." },
    ]
  },
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
  const [selectedAdapter, setSelectedAdapter] = useState<AdapterId | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);
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

  const handleCreateConnection = async () => {
    if (!businessId || !selectedAdapter) return;
    const adapter = ADAPTERS.find(a => a.id === selectedAdapter);
    if (!adapter) return;

    const requiredFields = adapter.fields.filter(f => f.required).map(f => f.key);
    const missing = requiredFields.filter(key => !formValues[key]?.trim());
    if (missing.length > 0) {
      setFormError(`Please fill in: ${missing.join(", ")}`);
      return;
    }

    setFormLoading(true);
    setFormError(null);

    try {
      const credentials: Record<string, string> = {};
      adapter.fields.forEach(field => {
        if (field.key !== "connection_name" && formValues[field.key]) {
          credentials[field.key] = formValues[field.key];
        }
      });

      await api.post("/pos/connections", {
        data: {
          adapter_type: selectedAdapter,
          connection_name: formValues.connection_name || adapter.name,
          sync_sales: true,
          sync_inventory: true,
          push_orders: false,
        },
        credentials,
      }, {
        params: { business_id: businessId },
      });

      setShowAddModal(false);
      setSelectedAdapter(null);
      setFormValues({});
      fetchConnections();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      setFormError(typeof detail === "string" ? detail : "Could not create connection. Check credentials and try again.");
    } finally {
      setFormLoading(false);
    }
  };

  const openAdapter = (adapterId: AdapterId) => {
    setSelectedAdapter(adapterId);
    setFormValues({});
    setFormError(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-12 h-12 rounded-xl bg-accent-blue animate-pulse" />
      </div>
    );
  }

  const saudiAdapters = ADAPTERS.filter(a => a.category === "Saudi-native");
  const globalAdapters = ADAPTERS.filter(a => a.category === "Global");
  const customAdapters = ADAPTERS.filter(a => a.category === "Custom");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-navy-text">Integrations</h1>
          <p className="text-sm text-navy-muted">
            Connect the tools you already use and let NazmOS turn their data into decisions.
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
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Link2 className="w-5 h-5 text-blue-400" />
            <span className="text-sm text-navy-muted">Active Connections</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">
            {connections.filter((c) => c.is_active).length}
          </p>
        </div>
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <RefreshCw className="w-5 h-5 text-green-400" />
            <span className="text-sm text-navy-muted">Last Sync</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">
            {connections[0]?.last_sync_at
              ? new Date(connections[0].last_sync_at).toLocaleTimeString()
              : "Never"}
          </p>
        </div>
        <div className="bg-navy-panel rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-2">
            <Zap className="w-5 h-5 text-purple-400" />
            <span className="text-sm text-navy-muted">Records Synced</span>
          </div>
          <p className="text-2xl font-bold text-navy-text">
            {connections.reduce((sum, c) => sum + (c.last_sync_records_processed || 0), 0)}
          </p>
        </div>
      </div>

      <div className="bg-navy-panel rounded-2xl overflow-hidden">
        <div className="p-4 border-b border-navy-panel-2">
          <h2 className="text-lg font-semibold text-navy-text">Connected Systems</h2>
        </div>
        
        {connections.length === 0 ? (
          <div className="p-12 text-center">
            <Link2 className="w-16 h-16 text-navy-faint mx-auto mb-4" />
            <p className="text-navy-muted mb-4">No integrations configured yet</p>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors"
            >
              Add Your First Integration
            </button>
          </div>
        ) : (
          <div className="divide-y divide-navy-panel-2">
            {connections.map((conn) => {
              const adapter = ADAPTERS.find((a) => a.id === conn.adapter_type);
              const AdapterIcon = adapter?.icon || Link2;
              
              return (
                <div key={conn.id} className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-navy-panel-2 flex items-center justify-center">
                      <AdapterIcon className="w-6 h-6 text-navy-muted" />
                    </div>
                    <div>
                      <p className="font-medium text-navy-text">{conn.connection_name}</p>
                      <p className="text-sm text-navy-muted">{adapter?.name}</p>
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
                        className="p-2 text-navy-muted hover:bg-navy-panel-2 rounded-lg transition-colors"
                        title="Test connection"
                      >
                        <Zap className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleSync(conn.id)}
                        disabled={conn.sync_status === "syncing"}
                        className="p-2 text-navy-muted hover:bg-navy-panel-2 rounded-lg transition-colors disabled:opacity-50"
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
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-navy-panel rounded-2xl p-6 w-full max-w-2xl max-h-[85vh] overflow-y-auto"
          >
            <h3 className="text-lg font-semibold text-navy-text mb-4">
              {selectedAdapter ? "Configure integration" : "Add Integration"}
            </h3>
            
            {!selectedAdapter ? (
              <div className="space-y-6">
                <AdapterGrid title="Saudi-native" adapters={saudiAdapters} onSelect={openAdapter} />
                <AdapterGrid title="Global platforms" adapters={globalAdapters} onSelect={openAdapter} />
                <AdapterGrid title="Custom" adapters={customAdapters} onSelect={openAdapter} />
                <button
                  onClick={() => setShowAddModal(false)}
                  className="w-full py-3 bg-navy-panel-2 text-navy-text rounded-xl hover:bg-navy-panel-3 transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div>
                <button
                  onClick={() => setSelectedAdapter(null)}
                  className="flex items-center gap-1 text-sm text-blue-400 mb-4 hover:text-blue-300"
                >
                  <ArrowLeft className="w-4 h-4" /> Back to integrations
                </button>
                
                <AdapterForm
                  adapter={ADAPTERS.find(a => a.id === selectedAdapter)!}
                  values={formValues}
                  onChange={setFormValues}
                  error={formError}
                />
                
                <div className="mt-6 flex gap-3">
                  <button
                    onClick={() => setSelectedAdapter(null)}
                    className="flex-1 py-3 bg-navy-panel-2 text-navy-text rounded-xl hover:bg-navy-panel-3 transition-colors"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleCreateConnection}
                    disabled={formLoading}
                    className="flex-1 py-3 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50"
                  >
                    {formLoading ? "Saving…" : "Connect"}
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

function AdapterGrid({ title, adapters, onSelect }: { title: string; adapters: AdapterConfig[]; onSelect: (id: AdapterId) => void }) {
  return (
    <div>
      <h4 className="text-sm font-medium text-navy-muted mb-3">{title}</h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {adapters.map((adapter) => {
          const Icon = adapter.icon;
          return (
            <button
              key={adapter.id}
              onClick={() => onSelect(adapter.id)}
              className="flex items-start gap-4 p-4 bg-navy-panel-2 rounded-xl hover:bg-navy-panel-3 transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-navy-panel flex items-center justify-center shrink-0">
                <Icon className="w-5 h-5 text-navy-muted" />
              </div>
              <div>
                <p className="font-medium text-navy-text">{adapter.name}</p>
                <p className="text-sm text-navy-muted">{adapter.description}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AdapterForm({ adapter, values, onChange, error }: { 
  adapter: AdapterConfig; 
  values: Record<string, string>; 
  onChange: (v: Record<string, string>) => void;
  error: string | null;
}) {
  return (
    <div className="space-y-4">
      {adapter.fields.map((field) => (
        <div key={field.key}>
          <label className="block text-sm font-medium text-navy-text mb-1.5">
            {field.label}
            {field.required && <span className="text-red-400 ml-1">*</span>}
          </label>
          <input
            type={field.type || "text"}
            value={values[field.key] || ""}
            onChange={(e) => onChange({ ...values, [field.key]: e.target.value })}
            placeholder={field.placeholder}
            className="w-full px-4 py-2.5 bg-navy-deep border border-navy-panel-2 rounded-xl text-navy-text placeholder-navy-faint focus:outline-none focus:border-blue-500"
          />
        </div>
      ))}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}
