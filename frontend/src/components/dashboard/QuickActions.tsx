import { Package, FileText, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

export function QuickActions() {
  const router = useRouter();

  const actions = [
    {
      icon: Package,
      label: "Restock Items",
      description: "Quick reorder",
      onClick: () => router.push("/inventory"),
      disabled: false,
      color: "text-accent-blue",
      bg: "bg-accent-blue/10",
    },
    {
      icon: FileText,
      label: "Reports",
      description: "Download",
      onClick: () => {},
      disabled: true,
      color: "text-text-muted",
      bg: "bg-surface",
    },
    {
      icon: MessageCircle,
      label: "Ask AI",
      description: "Phase 2",
      onClick: () => {},
      disabled: true,
      color: "text-text-muted",
      bg: "bg-surface",
    },
  ];

  return (
    <div>
      <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">
        Quick Actions
      </h3>
      <div className="grid grid-cols-3 gap-3">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              key={action.label}
              onClick={action.onClick}
              disabled={action.disabled}
              className={cn(
                "p-4 rounded-xl border border-border flex flex-col items-center gap-2 transition-all",
                action.disabled
                  ? "opacity-50 cursor-not-allowed"
                  : "hover:bg-surface-hover cursor-pointer"
              )}
            >
              <div className={cn("p-2 rounded-lg", action.bg)}>
                <Icon className={cn("w-5 h-5", action.color)} />
              </div>
              <span className="text-xs font-medium text-center">{action.label}</span>
              <span className="text-xs text-text-muted">{action.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
