"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Command, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon?: React.ReactNode;
  action: () => void;
  shortcut?: string;
}

interface CommandMenuProps {
  items: CommandItem[];
  isOpen: boolean;
  onClose: () => void;
}

export function CommandMenu({ items, isOpen, onClose }: CommandMenuProps) {
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filteredItems = items.filter(
    (item) =>
      item.label.toLowerCase().includes(query.toLowerCase()) ||
      item.description?.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelect = useCallback(
    (item: CommandItem) => {
      item.action();
      onClose();
      setQuery("");
    },
    [onClose]
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredItems.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredItems.length) % filteredItems.length);
      } else if (e.key === "Enter" && filteredItems[selectedIndex]) {
        handleSelect(filteredItems[selectedIndex]);
      }
    };

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, filteredItems, selectedIndex, handleSelect]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50"
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
        
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: -20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -20 }}
          transition={{ type: "spring", stiffness: 300, damping: 25 }}
          className="absolute top-[20%] left-1/2 -translate-x-1/2 w-full max-w-xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="bg-bg-secondary border border-border rounded-2xl shadow-2xl overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
              <Search className="w-5 h-5 text-text-muted" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Type a command or search..."
                className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted outline-none"
                autoFocus
              />
              <kbd className="px-2 py-1 bg-bg-tertiary rounded text-xs text-text-muted">
                ESC
              </kbd>
            </div>

            <div className="max-h-80 overflow-y-auto py-2">
              {filteredItems.length === 0 ? (
                <div className="px-4 py-8 text-center text-text-muted">
                  No results found
                </div>
              ) : (
                filteredItems.map((item, index) => (
                  <button
                    key={item.id}
                    onClick={() => handleSelect(item)}
                    onMouseEnter={() => setSelectedIndex(index)}
                    className={cn(
                      "w-full flex items-center gap-3 px-4 py-3 transition-colors",
                      index === selectedIndex
                        ? "bg-brand-primary/10 text-text-primary"
                        : "text-text-secondary hover:bg-bg-tertiary"
                    )}
                  >
                    {item.icon && (
                      <div className="w-8 h-8 rounded-lg bg-bg-tertiary flex items-center justify-center">
                        {item.icon}
                      </div>
                    )}
                    <div className="flex-1 text-left">
                      <div className="font-medium">{item.label}</div>
                      {item.description && (
                        <div className="text-sm text-text-muted">{item.description}</div>
                      )}
                    </div>
                    {item.shortcut && (
                      <kbd className="px-2 py-1 bg-bg-tertiary rounded text-xs text-text-muted">
                        {item.shortcut}
                      </kbd>
                    )}
                    {index === selectedIndex && (
                      <ArrowRight className="w-4 h-4 text-brand-primary" />
                    )}
                  </button>
                ))
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export function useCommandMenu(items: CommandItem[]) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen(true);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return { isOpen, setIsOpen, CommandMenu: () => (
    <CommandMenu items={items} isOpen={isOpen} onClose={() => setIsOpen(false)} />
  )};
}
