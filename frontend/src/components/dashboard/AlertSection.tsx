import { useRouter } from "next/navigation";
import { AlertCard } from "./AlertCard";
import { Skeleton } from "@/components/ui/Skeleton";
import { AlertsResponse } from "@/types/dashboard";

interface AlertSectionProps {
  alerts: AlertsResponse | null;
  isLoading: boolean;
}

export function AlertSection({ alerts, isLoading }: AlertSectionProps) {
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-32" />
        <div className="flex gap-3 overflow-x-auto pb-2">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="w-72 h-28 flex-shrink-0" />
          ))}
        </div>
      </div>
    );
  }

  if (!alerts || alerts.alerts.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
          Alerts ({alerts.alerts.length})
        </h3>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0 md:grid md:grid-cols-2 lg:grid-cols-3 md:overflow-visible">
        {alerts.alerts.slice(0, 6).map((alert) => (
          <AlertCard
            key={alert.id}
            alert={alert}
            onAction={() => {
              if (alert.item_id) {
                router.push(`/inventory?item=${alert.item_id}`);
              }
            }}
          />
        ))}
      </div>
    </div>
  );
}
