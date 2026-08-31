import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Display = forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <h1
        ref={ref}
        className={cn(
          "font-serif text-5xl md:text-6xl lg:text-7xl font-normal tracking-tight text-foreground",
          className
        )}
        {...props}
      >
        {children}
      </h1>
    );
  }
);

Display.displayName = "Display";

export const Heading = forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement> & { level?: 1 | 2 | 3 | 4 }>(
  ({ className, children, level = 2, ...props }, ref) => {
    const levels: Record<number, string> = {
      1: "font-serif text-4xl md:text-5xl font-normal tracking-tight",
      2: "font-serif text-3xl md:text-4xl font-normal tracking-tight",
      3: "font-sans text-xl md:text-2xl font-medium tracking-tight",
      4: "font-sans text-lg font-medium tracking-tight",
    };

    return (
      <h1
        ref={ref}
        className={cn(levels[level], "text-foreground", className)}
        {...props}
      >
        {children}
      </h1>
    );
  }
);

Heading.displayName = "Heading";

export const Body = forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement> & { size?: 'sm' | 'md' | 'lg' }>(
  ({ className, children, size = "md", ...props }, ref) => {
    const sizes: Record<string, string> = {
      sm: "text-sm leading-relaxed",
      md: "text-base leading-relaxed",
      lg: "text-lg leading-relaxed",
    };

    return (
      <p
        ref={ref}
        className={cn("font-sans text-muted-foreground", sizes[size], className)}
        {...props}
      >
        {children}
      </p>
    );
  }
);

Body.displayName = "Body";

export const Label = forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <label
        ref={ref}
        className={cn(
          "font-sans text-xs font-medium uppercase tracking-widest text-muted-foreground",
          className
        )}
        {...props}
      >
        {children}
      </label>
    );
  }
);

Label.displayName = "Label";

export const Number = forwardRef<HTMLSpanElement, React.HTMLAttributes<HTMLSpanElement>>(
  ({ className, children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn("font-mono tabular-nums text-foreground", className)}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Number.displayName = "Number";
