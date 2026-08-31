import type { Config } from "tailwindcss";

// AUTO-GENERATED from design-tokens/tokens.json via scripts/build_design_tokens.ts - DO NOT EDIT.
const config: Config = {
  "darkMode": [
    "class"
  ],
  "content": [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  "theme": {
    "container": {
      "center": true,
      "padding": "2rem",
      "screens": {
        "2xl": "1400px"
      }
    },
    "extend": {
      "colors": {
        "card": {
          "DEFAULT": "oklch(var(--card) / <alpha-value>)",
          "foreground": "oklch(var(--card-foreground) / <alpha-value>)"
        },
        "popover": {
          "DEFAULT": "oklch(var(--popover) / <alpha-value>)",
          "foreground": "oklch(var(--popover-foreground) / <alpha-value>)"
        },
        "primary": {
          "DEFAULT": "oklch(var(--primary) / <alpha-value>)",
          "foreground": "oklch(var(--primary-foreground) / <alpha-value>)"
        },
        "secondary": {
          "DEFAULT": "oklch(var(--secondary) / <alpha-value>)",
          "foreground": "oklch(var(--secondary-foreground) / <alpha-value>)"
        },
        "destructive": {
          "DEFAULT": "oklch(var(--destructive) / <alpha-value>)",
          "foreground": "oklch(var(--destructive-foreground) / <alpha-value>)"
        },
        "muted": {
          "DEFAULT": "oklch(var(--muted) / <alpha-value>)",
          "foreground": "oklch(var(--muted-foreground) / <alpha-value>)"
        },
        "warning": {
          "DEFAULT": "oklch(var(--warning) / <alpha-value>)",
          "foreground": "oklch(var(--warning-foreground) / <alpha-value>)"
        },
        "success": {
          "DEFAULT": "oklch(var(--success) / <alpha-value>)",
          "foreground": "oklch(var(--success-foreground) / <alpha-value>)"
        },
        "accent": {
          "DEFAULT": "oklch(var(--accent-primary) / <alpha-value>)",
          "foreground": "oklch(var(--accent-foreground) / <alpha-value>)",
          "surface": "oklch(var(--accent) / <alpha-value>)",
          "primary": "oklch(var(--accent-primary) / <alpha-value>)",
          "primary-hover": "oklch(var(--accent-primary-hover) / <alpha-value>)",
          "secondary": "oklch(var(--accent-secondary) / <alpha-value>)",
          "secondary-hover": "oklch(var(--accent-secondary-hover) / <alpha-value>)",
          "blue": "oklch(var(--accent-blue) / <alpha-value>)",
          "green": "oklch(var(--accent-green) / <alpha-value>)",
          "yellow": "oklch(var(--accent-yellow) / <alpha-value>)",
          "red": "oklch(var(--accent-red) / <alpha-value>)",
          "purple": "oklch(var(--accent-purple) / <alpha-value>)",
          "orange": "oklch(var(--accent-orange) / <alpha-value>)"
        },
        "background": "oklch(var(--background) / <alpha-value>)",
        "foreground": "oklch(var(--foreground) / <alpha-value>)",
        "input": "oklch(var(--input) / <alpha-value>)",
        "ring": "oklch(var(--ring) / <alpha-value>)",
        "border": "oklch(var(--border) / <alpha-value>)",
        "success-bright": "oklch(var(--success-bright) / <alpha-value>)",
        "chart-1": "oklch(var(--chart-1) / <alpha-value>)",
        "chart-2": "oklch(var(--chart-2) / <alpha-value>)",
        "chart-3": "oklch(var(--chart-3) / <alpha-value>)",
        "chart-4": "oklch(var(--chart-4) / <alpha-value>)",
        "chart-5": "oklch(var(--chart-5) / <alpha-value>)",
        "chart-grid": "oklch(var(--chart-grid) / <alpha-value>)",
        "surface-hover": "oklch(var(--surface-hover) / <alpha-value>)",
        "overlay": "var(--overlay)",
        "glass": "var(--glass)",
        "glass-border": "var(--glass-border)",
        "brand": {
          "primary": "oklch(var(--brand-primary) / <alpha-value>)",
          "secondary": "oklch(var(--brand-secondary) / <alpha-value>)",
          "accent": "oklch(var(--brand-accent) / <alpha-value>)",
          "teal": "oklch(var(--brand-teal) / <alpha-value>)",
          "teal-light": "oklch(var(--brand-teal-light) / <alpha-value>)",
          "teal-dark": "oklch(var(--brand-teal-dark) / <alpha-value>)",
          "amber": "oklch(var(--brand-amber) / <alpha-value>)",
          "gold": "oklch(var(--brand-gold) / <alpha-value>)",
          "gold-soft": "oklch(var(--brand-gold-soft) / <alpha-value>)",
          "green": "oklch(var(--brand-green) / <alpha-value>)",
          "green-light": "oklch(var(--brand-green-light) / <alpha-value>)",
          "red": "oklch(var(--brand-red) / <alpha-value>)",
          "red-light": "oklch(var(--brand-red-light) / <alpha-value>)",
          "night": "oklch(var(--brand-night) / <alpha-value>)",
          "cream": "oklch(var(--brand-cream) / <alpha-value>)",
          "cream-dark": "oklch(var(--brand-cream-dark) / <alpha-value>)",
          "sand": "oklch(var(--brand-sand) / <alpha-value>)"
        },
        "intelligence": {
          "DEFAULT": "oklch(var(--intelligence) / <alpha-value>)",
          "muted": "oklch(var(--intelligence-muted) / <alpha-value>)",
          "surface": "oklch(var(--intelligence-surface) / <alpha-value>)",
          "border": "oklch(var(--intelligence-border) / <alpha-value>)"
        },
        "chat": {
          "deep": "oklch(var(--chat-deep) / <alpha-value>)",
          "steel": "oklch(var(--chat-steel) / <alpha-value>)",
          "warm": "oklch(var(--chat-warm) / <alpha-value>)"
        },
        "whatsapp": {
          "DEFAULT": "var(--whatsapp)",
          "deep": "oklch(var(--whatsapp-deep) / <alpha-value>)",
          "light": "oklch(var(--whatsapp-light) / <alpha-value>)",
          "faint": "oklch(var(--whatsapp-faint) / <alpha-value>)",
          "mid": "oklch(var(--whatsapp-mid) / <alpha-value>)",
          "bright": "oklch(var(--whatsapp-bright) / <alpha-value>)"
        }
      },
      "borderRadius": {
        "none": "0px",
        "sm": "0.25rem",
        "default": "0.375rem",
        "md": "0.375rem",
        "lg": "0.5rem",
        "xl": "0.5rem",
        "2xl": "0.5rem",
        "3xl": "0.5rem"
      },
      "fontFamily": {
        "sans": [
          "var(--font-sans)",
          "Inter",
          "system-ui",
          "sans-serif"
        ],
        "serif": [
          "var(--font-serif)",
          "Georgia",
          "serif"
        ],
        "mono": [
          "var(--font-mono)",
          "JetBrains Mono",
          "monospace"
        ],
        "arabic": [
          "var(--font-arabic)",
          "IBM Plex Sans Arabic",
          "Tahoma",
          "sans-serif"
        ]
      },
      "fontSize": {
        "xs": [
          "0.75rem",
          {
            "lineHeight": "1.5"
          }
        ],
        "sm": [
          "0.875rem",
          {
            "lineHeight": "1.5"
          }
        ],
        "base": [
          "1rem",
          {
            "lineHeight": "1.6"
          }
        ],
        "lg": [
          "1.25rem",
          {
            "lineHeight": "1.5"
          }
        ],
        "xl": [
          "1.5625rem",
          {
            "lineHeight": "1.4"
          }
        ],
        "2xl": [
          "1.9375rem",
          {
            "lineHeight": "1.3"
          }
        ],
        "3xl": [
          "2.4375rem",
          {
            "lineHeight": "1.2"
          }
        ],
        "4xl": [
          "3.0625rem",
          {
            "lineHeight": "1.15"
          }
        ],
        "5xl": [
          "3.8125rem",
          {
            "lineHeight": "1.1"
          }
        ],
        "6xl": [
          "4.75rem",
          {
            "lineHeight": "1.05"
          }
        ],
        "7xl": [
          "5.9375rem",
          {
            "lineHeight": "1.0"
          }
        ],
        "8xl": [
          "7.4375rem",
          {
            "lineHeight": "1.0"
          }
        ],
        "9xl": [
          "9.3125rem",
          {
            "lineHeight": "1.0"
          }
        ]
      },
      "boxShadow": {
        "card": "0 10px 40px oklch(0% 0 0 / 0.2)",
        "glow-gold": "0 0 24px 0 oklch(75.41% 0.085 67.1 / 0.25)",
        "glow-teal": "0 0 24px 0 oklch(70.38% 0.123 182.5 / 0.25)",
        "elevation-1": "0 1px 2px oklch(0% 0 0 / 0.3)",
        "elevation-2": "0 1px 2px oklch(0% 0 0 / 0.3), 0 8px 24px -8px oklch(0% 0 0 / 0.45)",
        "elevation-3": "0 1px 2px oklch(0% 0 0 / 0.3), 0 8px 24px -8px oklch(0% 0 0 / 0.45), 0 24px 48px -12px oklch(0% 0 0 / 0.6), inset 0 1px 0 oklch(100% 0 0 / 0.04)"
      },
      "keyframes": {
        "accordion-down": {
          "from": {
            "height": "0"
          },
          "to": {
            "height": "var(--radix-accordion-content-height)"
          }
        },
        "accordion-up": {
          "from": {
            "height": "var(--radix-accordion-content-height)"
          },
          "to": {
            "height": "0"
          }
        },
        "fade-in": {
          "0%": {
            "opacity": "0"
          },
          "100%": {
            "opacity": "1"
          }
        },
        "fade-in-up": {
          "0%": {
            "opacity": "0",
            "transform": "translateY(20px)"
          },
          "100%": {
            "opacity": "1",
            "transform": "translateY(0)"
          }
        },
        "fade-in-down": {
          "0%": {
            "opacity": "0",
            "transform": "translateY(-20px)"
          },
          "100%": {
            "opacity": "1",
            "transform": "translateY(0)"
          }
        },
        "slide-in-left": {
          "0%": {
            "opacity": "0",
            "transform": "translateX(-20px)"
          },
          "100%": {
            "opacity": "1",
            "transform": "translateX(0)"
          }
        },
        "slide-in-right": {
          "0%": {
            "opacity": "0",
            "transform": "translateX(20px)"
          },
          "100%": {
            "opacity": "1",
            "transform": "translateX(0)"
          }
        },
        "scale-in": {
          "0%": {
            "opacity": "0",
            "transform": "scale(0.95)"
          },
          "100%": {
            "opacity": "1",
            "transform": "scale(1)"
          }
        },
        "float": {
          "0%, 100%": {
            "transform": "translateY(0px)"
          },
          "50%": {
            "transform": "translateY(-10px)"
          }
        },
        "weave-in": {
          "0%": {
            "opacity": "0"
          },
          "100%": {
            "opacity": "1"
          }
        },
        "seam-reveal": {
          "0%": {
            "opacity": "0",
            "stroke-dashoffset": "1"
          },
          "100%": {
            "opacity": "1",
            "stroke-dashoffset": "0"
          }
        }
      },
      "animation": {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "fade-in": "fade-in 0.5s ease-out forwards",
        "fade-in-up": "fadeInUp 0.5s ease-out forwards",
        "fade-in-down": "fadeInDown 0.5s ease-out forwards",
        "slide-in-left": "slideInLeft 0.5s ease-out forwards",
        "slide-in-right": "slideInRight 0.5s ease-out forwards",
        "scale-in": "scaleIn 0.3s ease-out forwards",
        "float": "float 6s ease-in-out infinite",
        "weave-in": "weave-in var(--duration-weave) linear",
        "seam-reveal": "seam-reveal var(--duration-seam) ease-out forwards"
      }
    }
  },
  "plugins": []
};
config.plugins = [require("tailwindcss-animate")];

export default config;
