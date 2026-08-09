"use client";

import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToastProps {
  message: string;
  type?: "success" | "error" | "warning" | "info";
  onClose: () => void;
  duration?: number;
}

export function Toast({ message, type = "info", onClose, duration = 5000 }: ToastProps) {
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
      setTimeout(onClose, 300);
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const toastStyles = {
    success: "bg-status-success/10 border-status-success/30 text-status-success",
    error: "bg-status-error/10 border-status-error/30 text-status-error",
    warning: "bg-status-warning/10 border-status-warning/30 text-status-warning",
    info: "bg-status-info/10 border-status-info/30 text-status-info",
  };

  return (
    <div
      className={cn(
        "fixed bottom-4 right-4 z-50 transition-all duration-300",
        isVisible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      )}
    >
      <div
        className={cn(
          "px-4 py-3 rounded-xl shadow-lg border flex items-center gap-3 min-w-[300px]",
          toastStyles[type]
        )}
      >
        <span className="flex-1">{message}</span>
        <button onClick={onClose} className="hover:opacity-70 transition-opacity" aria-label="Close notification">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

import { createContext, useContext, useState as useStateContext, useCallback, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, AlertCircle, AlertTriangle, Info } from "lucide-react";

type ToastType = "success" | "error" | "warning" | "info";

interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  description?: string;
  duration?: number;
}

interface ToastContextType {
  toasts: ToastItem[];
  addToast: (toast: Omit<ToastItem, "id">) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToastContext() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useStateContext<ToastItem[]>([]);

  const addToast = useCallback((toast: Omit<ToastItem, "id">) => {
    const id = String(Date.now());
    setToasts((prev) => [...prev, { ...toast, id }]);

    if (toast.duration !== 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, toast.duration || 5000);
    }
  }, [setToasts]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, [setToasts]);

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
      <ToastContainer />
    </ToastContext.Provider>
  );
}

function ToastContainer() {
  const { toasts, removeToast } = useToastContext();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      <AnimatePresence>
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
        ))}
      </AnimatePresence>
    </div>
  );
}

const toastConfig = {
  success: {
    icon: CheckCircle,
    className: "border-status-success/30 bg-status-success/10",
    iconClass: "text-status-success",
  },
  error: {
    icon: AlertCircle,
    className: "border-status-error/30 bg-status-error/10",
    iconClass: "text-status-error",
  },
  warning: {
    icon: AlertTriangle,
    className: "border-status-warning/30 bg-status-warning/10",
    iconClass: "text-status-warning",
  },
  info: {
    icon: Info,
    className: "border-status-info/30 bg-status-info/10",
    iconClass: "text-status-info",
  },
};

function ToastItem({ toast, onClose }: { toast: ToastItem; onClose: () => void }) {
  const config = toastConfig[toast.type];
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: 100, scale: 0.9 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 100, scale: 0.9 }}
      transition={{ type: "spring", stiffness: 300, damping: 25 }}
      className={cn(
        "flex items-start gap-3 p-4 rounded-xl border shadow-xl shadow-brand-night/20 backdrop-blur-sm min-w-[320px] max-w-md bg-bg-secondary",
        config.className
      )}
    >
      <Icon className={cn("w-5 h-5 mt-0.5 flex-shrink-0", config.iconClass)} />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-text-primary">{toast.title}</div>
        {toast.description && (
          <div className="text-sm text-text-secondary mt-0.5">{toast.description}</div>
        )}
      </div>
      <button
        onClick={onClose}
        className="text-text-muted hover:text-text-secondary transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </motion.div>
  );
}
