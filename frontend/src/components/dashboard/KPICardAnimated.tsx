"use client";

import { useEffect, useState, useRef } from "react";
import { motion, useSpring, useTransform, useInView } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface KPICardAnimatedProps {
  label: string;
  value: number;
  previousValue?: number;
  format?: "currency" | "number" | "percentage";
  sparklineData?: number[];
  colorScheme?: "blue" | "green" | "yellow" | "purple";
  loading?: boolean;
  className?: string;
}

export function KPICardAnimated({
  label,
  value,
  previousValue,
  format = "currency",
  sparklineData,
  colorScheme = "blue",
  loading = false,
  className,
}: KPICardAnimatedProps) {
  const cardRef = useRef(null);
  const isInView = useInView(cardRef, { once: true, amount: 0.5 });

  const springValue = useSpring(0, { stiffness: 100, damping: 30 });
  const [displayValue, setDisplayValue] = useState("0");

  useEffect(() => {
    if (isInView && !loading) {
      const duration = 1000;
      const startTime = Date.now();
      const startValue = 0;

      const animate = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = startValue + (value - startValue) * easeOut;

        if (format === "currency") {
          setDisplayValue(`﷼ ${Math.round(current).toLocaleString("ar-SA")}`);
        } else if (format === "percentage") {
          setDisplayValue(`${current.toFixed(1)}%`);
        } else {
          setDisplayValue(Math.round(current).toLocaleString("ar-SA"));
        }

        if (progress < 1) {
          requestAnimationFrame(animate);
        }
      };

      springValue.set(value);
      requestAnimationFrame(animate);
    }
  }, [isInView, value, loading, format, springValue]);

  const change = previousValue ? ((value - previousValue) / previousValue) * 100 : 0;
  const changeDirection = change > 0 ? "up" : change < 0 ? "down" : "neutral";

  const colorClasses = {
    blue: "border-l-brand-primary",
    green: "border-l-status-success",
    yellow: "border-l-status-warning",
    purple: "border-l-brand-secondary",
  };

  const changeColors = {
    up: "text-status-success bg-status-success/10",
    down: "text-status-error bg-status-error/10",
    neutral: "text-text-muted bg-bg-tertiary",
  };

  if (loading) {
    return (
      <div className={cn("p-5 rounded-xl bg-bg-secondary border border-border animate-pulse", className)}>
        <div className="h-4 w-24 bg-bg-tertiary rounded mb-4" />
        <div className="h-8 w-32 bg-bg-tertiary rounded mb-4" />
        <div className="h-6 w-full bg-bg-tertiary rounded" />
      </div>
    );
  }

  return (
    <motion.div
      ref={cardRef}
      initial={{ opacity: 0, y: 20 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      whileHover={{ y: -2, boxShadow: "0 10px 40px rgba(0, 0, 0, 0.2)" }}
      transition={{ duration: 0.5 }}
      className={cn(
        "relative p-5 rounded-xl bg-bg-secondary border border-border border-l-[3px] transition-shadow cursor-default",
        colorClasses[colorScheme],
        className
      )}
      data-tour="dashboard"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          {label}
        </span>

        {previousValue !== undefined && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className={cn(
              "flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium",
              changeColors[changeDirection]
            )}
          >
            {changeDirection === "up" && <TrendingUp size={12} />}
            {changeDirection === "down" && <TrendingDown size={12} />}
            {changeDirection === "neutral" && <Minus size={12} />}
            <span>{Math.abs(change).toFixed(1)}%</span>
          </motion.div>
        )}
      </div>

      <motion.div className="text-3xl font-bold font-mono text-text-primary mb-3">
        {displayValue}
      </motion.div>

      <div className="flex items-end justify-between">
        {sparklineData && sparklineData.length > 0 && (
          <Sparkline data={sparklineData} color={colorScheme} />
        )}

        {previousValue !== undefined && (
          <span className="text-xs text-text-muted">
            vs ﷼ {previousValue.toLocaleString("ar-SA")}
          </span>
        )}
      </div>
    </motion.div>
  );
}

function Sparkline({ data, color }: { data: number[]; color: "blue" | "green" | "yellow" | "purple" }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * 100;
    const y = 100 - ((value - min) / range) * 100;
    return `${x},${y}`;
  }).join(" ");

  const gradientId = `sparkline-gradient-${color}`;

  const colors = {
    blue: { stroke: "#6366f1", fill: "rgba(99, 102, 241, 0.2)" },
    green: { stroke: "#22c55e", fill: "rgba(34, 197, 94, 0.2)" },
    yellow: { stroke: "#eab308", fill: "rgba(234, 179, 8, 0.2)" },
    purple: { stroke: "#8b5cf6", fill: "rgba(139, 92, 246, 0.2)" },
  };

  const currentColor = colors[color];

  return (
    <svg className="w-24 h-8" viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={currentColor.fill} />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>

      <polygon points={`0,100 ${points} 100,100`} fill={`url(#${gradientId})`} />

      <polyline
        points={points}
        fill="none"
        stroke={currentColor.stroke}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
