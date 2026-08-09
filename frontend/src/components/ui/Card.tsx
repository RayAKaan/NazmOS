import { HTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "bordered";
  hoverable?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = "default", hoverable = false, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "bg-card border border-border",
          "shadow-card",
          hoverable && "transition-colors duration-200 hover:bg-muted/50",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = "Card";

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div 
      className={cn("p-6 border-b border-border", className)} 
      {...props} 
    />
  );
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 
      className={cn("font-sans text-lg font-medium text-foreground", className)} 
      {...props} 
    />
  );
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p 
      className={cn("text-sm text-muted-foreground mt-1", className)} 
      {...props} 
    />
  );
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div 
      className={cn("p-6", className)} 
      {...props} 
    />
  );
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div 
      className={cn("p-6 pt-0 flex items-center gap-2", className)} 
      {...props} 
    />
  );
}
