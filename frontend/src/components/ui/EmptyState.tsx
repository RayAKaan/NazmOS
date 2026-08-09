import Link from "next/link";
import { ArrowRight, LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateAction {
  label: string;
  href: string;
  primary?: boolean;
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actions?: EmptyStateAction[];
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, actions, className }: EmptyStateProps) {
  return (
    <section
      className={cn(
        "flex flex-col items-center justify-center rounded-3xl border border-brand-cream/10 bg-brand-night px-6 py-14 text-center text-brand-cream",
        className
      )}
    >
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-amber/10">
        <Icon className="h-7 w-7 text-brand-amber" aria-hidden />
      </div>
      <h2 className="mt-5 text-xl font-bold text-brand-cream">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-brand-cream/62">{description}</p>
      {actions && actions.length > 0 && (
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          {actions.map((action) => (
            <Link
              key={action.href}
              href={action.href}
              className={
                action.primary
                  ? "inline-flex items-center justify-center gap-2 rounded-xl bg-brand-amber px-5 py-3 font-bold text-brand-night hover:bg-brand-gold"
                  : "inline-flex items-center justify-center gap-2 rounded-xl border border-brand-cream/10 px-5 py-3 font-bold text-brand-cream/75 hover:bg-brand-cream/5 hover:text-brand-cream"
              }
            >
              {action.label}
              {action.primary && <ArrowRight className="h-4 w-4" aria-hidden />}
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
