import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/utils";

interface HealthScoreProps {
  score: number | null;
  isLoading: boolean;
}

export function HealthScore({ score, isLoading }: HealthScoreProps) {
  if (isLoading) {
    return <Skeleton className="w-full h-48" />;
  }

  if (score === null) return null;

  const getScoreColor = (s: number) => {
    if (s >= 70) return "text-accent-green";
    if (s >= 50) return "text-accent-yellow";
    return "text-accent-red";
  };

  const getScoreBg = (s: number) => {
    if (s >= 70) return "bg-accent-green/10 border-accent-green/30";
    if (s >= 50) return "bg-accent-yellow/10 border-accent-yellow/30";
    return "bg-accent-red/10 border-accent-red/30";
  };

  const circumference = 2 * Math.PI * 45;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="bg-surface rounded-xl border border-border p-6">
      <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">
        Store Health
      </h3>
      <div className="flex items-center justify-center">
        <div className="relative">
          <svg className="w-32 h-32 -rotate-90" aria-hidden="true">
            <circle
              cx="64"
              cy="64"
              r="45"
              strokeWidth="10"
              stroke="var(--chart-grid)"
              fill="none"
            />
            <circle
              cx="64"
              cy="64"
              r="45"
              strokeWidth="10"
              stroke="currentColor"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              strokeLinecap="round"
              fill="none"
              className={cn("transition-all duration-1000", getScoreColor(score))}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={cn("text-3xl font-bold", getScoreColor(score))}>
              {score}
            </span>
          </div>
        </div>
      </div>
      <div className="mt-4 flex justify-center">
        <span
          className={cn(
            "px-3 py-1 rounded-full text-sm font-medium",
            getScoreBg(score)
          )}
        >
          {score >= 70
            ? "Excellent"
            : score >= 50
            ? "Needs Attention"
            : "Critical"}
        </span>
      </div>
    </div>
  );
}
