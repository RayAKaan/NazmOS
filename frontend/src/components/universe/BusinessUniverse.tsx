"use client";

import { useEffect, useReducer, useState, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useI18n } from "@/lib/i18n";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { ShaderBackground } from "./ShaderBackground";
import { UniverseScene } from "./UniverseScene";
import { UniverseMinimap } from "./Minimap";
import { UniverseControls } from "./UniverseControls";
import { CompanyOverlay } from "./CompanyOverlay";
import { DomainFocus, NazmosConvergence } from "./FocusOverlays";
import { AuditLayer } from "./AuditLayer";
import { INITIAL_STATE, universeReducer } from "./UniverseState";
import { type DomainId, type NodeId, type UniverseState } from "./data";

const EASE = [0.22, 1, 0.36, 1] as const;

type NavTarget = "universe" | "nazmos" | "audit" | "company";

function useWebGlSupport(): boolean | null {
  const [supported, setSupported] = useState<boolean | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    let yes = false;
    try {
      const c = document.createElement("canvas");
      yes = !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch {
      yes = false;
    }
    setSupported(yes);
  }, []);
  return supported;
}

export function BusinessUniverse() {
  const { t } = useI18n();
  const reduced = useReducedMotion();
  const webgl = useWebGlSupport();

  const [state, dispatch] = useReducer(universeReducer, INITIAL_STATE);

  // ── Theme: two first-class worlds (dark / light), one universe (spec §02).
  // The theme system (document.documentElement.dark + `nazmos-theme` storage)
  // is authoritative once the visitor has a preference. Brand-new visitors get
  // the flagship dark world until they choose — so `/` is dark by default but
  // never forced. Resolving in the initializer means the shader mounts with
  // the right world on the very first hydration frame (no flash).
  const getInitialTheme = (): "dark" | "light" => {
    if (typeof window === "undefined") return "dark";
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("nazmos-theme");
    } catch {
      /* storage unavailable */
    }
    if (stored === "light") return "light";
    if (stored === "dark") return "dark";
    if (stored === "system") {
      try {
        return window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
      } catch {
        /* matchMedia unavailable */
      }
    }
    return "dark";
  };
  const [theme, setTheme] = useState<"dark" | "light">(getInitialTheme);
  useEffect(() => {
    // No stored preference at all → the dark world is the flagship even when
    // the OS prefers light. The moment the visitor touches the switch, their
    // explicit choice wins and this effectively stops running.
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("nazmos-theme");
    } catch {
      /* storage unavailable */
    }
    if (stored === null) document.documentElement.classList.add("dark");
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.classList.toggle("dark", next === "dark");
      try {
        localStorage.setItem("nazmos-theme", next);
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  }, []);

  const selectNode = useCallback((node: NodeId) => dispatch({ type: "SELECT", node }), []);
  const goCompany = useCallback(() => dispatch({ type: "TO_COMPANY" }), []);
  const goNazmos = useCallback(() => dispatch({ type: "TO_NAZMOS" }), []);
  const goAudit = useCallback(() => dispatch({ type: "TO_AUDIT" }), []);
  const goBack = useCallback(() => dispatch({ type: "BACK" }), []);
  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  // --- Keyboard: ESC returns; Enter/Space activates the focused node (native
  // button behaviour); nothing else hijacked.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        goBack();
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goBack]);

  // --- Scroll lock while a focused panel is open (with graceful release) ----
  useEffect(() => {
    if (state.kind === "universe") return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [state.kind]);

  const current: NavTarget =
    state.kind === "audit"
      ? "audit"
      : state.kind === "nazmos"
        ? "nazmos"
        : state.kind === "company"
          ? "company"
          : "universe";

  const onNav = useCallback(
    (target: NavTarget) => {
      if (target === "universe") reset();
      else if (target === "nazmos") goNazmos();
      else if (target === "audit") goAudit();
      else if (target === "company") goCompany();
    },
    [reset, goNazmos, goAudit, goCompany],
  );

  // Render the background and scene only when meaningful. Show a static,
  // accessible fallback when WebGL is unavailable OR reduced motion is active
  // (the fallback is the SEO/a11y-safe, non-animating layer).
  const showShader = webgl === true && !reduced;

  return (
    <div className="obsidian-bg relative h-[100dvh] w-full overflow-hidden">
      {/* Background field */}
      <div className="absolute inset-0" aria-hidden="true">
        {showShader ? (
          <ShaderBackground theme={theme} state={state.kind} className="h-full w-full" />
        ) : (
          <UniverseFallback theme={theme} state={state.kind} />
        )}
      </div>

      {/* Top nav */}
      <UniverseControls
        current={current}
        theme={theme}
        onToggleTheme={toggleTheme}
        onNav={onNav}
      />

      {/* Center stage: scene + the state routes */}
      <main id="main" className="relative z-10 flex h-full">
        <div className="relative mx-auto flex w-full max-w-7xl flex-col px-5 pt-24 md:px-8">
          {/* Level 1 thesis — environment typography, shown in the universe */}
          <AnimatePresence mode="wait">
            {state.kind === "universe" && (
              <motion.div
                key="thesis"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.5, ease: EASE }}
                className="pointer-events-none mx-auto max-w-3xl pb-6 text-center"
              >
                <h1 className="u-ink font-serif text-4xl leading-[1.05] md:text-[3.4rem]">
                  {t.universe.thesisLead} <span className="u-teal">{t.universe.thesisBold}</span>
                </h1>
                <p className="u-ink-dim mx-auto mt-4 max-w-2xl text-sm leading-relaxed md:text-base">
                  {t.universe.spatialHint}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* The relationship network — persistent across all states */}
          <div className="relative flex-1">
            <UniverseScene
              state={state}
              onSelect={selectNode}
              className="absolute inset-0"
            />

            {/* Level 2 — the company, resting over the recessed network */}
            <AnimatePresence mode="wait">
              {state.kind === "company" && (
                <CompanyOverlay key="company" goNazmos={goNazmos} goBack={goBack} />
              )}
            </AnimatePresence>

            {/* Right-side (or stacked-on-mobile) dominant focus panels */}
            <AnimatePresence mode="wait">
              {state.kind === "domain" && (
                <DomainFocus
                  key="domain"
                  domain={state.domain as DomainId}
                  stacked={false}
                  goNazmos={goNazmos}
                  goBack={goBack}
                />
              )}
              {state.kind === "nazmos" && (
                <NazmosConvergence
                  key="nazmos"
                  stacked={false}
                  goAudit={goAudit}
                  goBack={goBack}
                />
              )}
            </AnimatePresence>

            <AnimatePresence mode="wait">
              {state.kind === "audit" && (
                <AuditLayer key="audit" stacked={false} onBack={goBack} />
              )}
            </AnimatePresence>
          </div>

          {/* Bottom hint */}
          <div className="pointer-events-none pb-6 text-center">
            <AnimatePresence mode="wait">
              {state.kind === "universe" ? (
                <motion.p
                  key="hint"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="u-ink-faint font-mono text-[11px] uppercase tracking-[0.2em]"
                >
                  {t.universe.hint}
                </motion.p>
              ) : state.kind === "domain" ? (
                <motion.p
                  key="hint2"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="u-ink-faint font-mono text-[11px] uppercase tracking-[0.2em]"
                >
                  {t.universe.focus.toward}
                </motion.p>
              ) : (
                <motion.button
                  key="return"
                  type="button"
                  onClick={reset}
                  className="focus-ring pointer-events-auto u-teal-deep font-mono text-[11px] uppercase tracking-[0.2em] hover:u-teal focus:outline-none"
                >
                  {t.universe.backToUniverse}
                </motion.button>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>

      {/* Minimap */}
      <UniverseMinimap state={state} onSelect={selectNode} />
    </div>
  );
}

/**
 * UniverseFallback — plain 2D presentation of the network as an SVG, used when
 * WebGL is unavailable or reduced motion is preferred. It is the SEO/a11y-safe
 * representation and carries the pauses without changing any meaning. The DOM
 * overlays (company, domain focus, NazmOS, audit) render on top of it as usual.
 */
function UniverseFallback({ theme, state }: { theme: "dark" | "light"; state: "universe" | "domain" | "company" | "nazmos" | "audit" }) {
  const { t, dir } = useI18n();
  const rtl = dir === "rtl";

  // Both fallback worlds share the same relationship structure; the material
  // changes (spec §43: fallback works in dark AND light with gold visible).
  const c =
    theme === "dark"
      ? {
          edge: "rgba(45,140,148,0.32)",
          edgeGold: "rgba(181,123,32,0.55)",
          teal: "rgb(21,155,141)",
          gold: "rgb(214,162,58)",
          ivory: "rgba(232,224,207,0.55)",
          ivoryDim: "rgba(232,224,207,0.25)",
        }
      : {
          edge: "rgba(45,119,112,0.32)",
          edgeGold: "rgba(185,125,31,0.5)",
          teal: "rgb(45,119,112)",
          gold: "rgb(201,148,50)",
          ivory: "rgba(243,239,229,0.95)",
          ivoryDim: "rgba(11,55,53,0.35)",
        };

  const dim = state === "company" ? 0.45 : 1;
  const nodes: { id: NodeId; label: string }[] = [
    { id: "nazmos", label: t.universe.nodes.nazmos.label },
    { id: "demand", label: t.universe.nodes.demand.label },
    { id: "suppliers", label: t.universe.nodes.suppliers.label },
    { id: "sales", label: t.universe.nodes.sales.label },
    { id: "inventory", label: t.universe.nodes.inventory.label },
    { id: "cost", label: t.universe.nodes.cost.label },
  ];

  const dot = (id: NodeId) => {
    const p = requirePos(id, rtl);
    return { x: p.x, y: p.y };
  };

  return (
    <svg
      className="h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
      style={{ opacity: dim }}
    >
      {EDGES_FALLBACK.map((e) => {
        const a = dot(e.a);
        const b = dot(e.b);
        const isValue = e.a === "nazmos" || e.b === "nazmos";
        return (
          <line
            key={`${e.a}|${e.b}`}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={isValue ? c.edgeGold : c.edge}
            strokeWidth={isValue ? 0.65 : 0.4}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
      {nodes.map((n) => {
        const p = dot(n.id);
        const isNazmos = n.id === "nazmos";
        return (
          <g key={n.id} transform={`translate(${p.x} ${p.y})`}>
            {isNazmos && (
              <circle r={3.6} fill="none" stroke={c.gold} strokeWidth="0.35" vectorEffect="non-scaling-stroke" />
            )}
            <circle
              r={isNazmos ? 2.1 : n.id === "audit" ? 0 : 1.3}
              fill={isNazmos ? c.gold : c.ivory}
              opacity={isNazmos ? 1 : 0.85}
            />
          </g>
        );
      })}
    </svg>
  );
}

function requirePos(id: NodeId, rtl: boolean) {
  const p = { x: 50, y: 58 };
  switch (id) {
    case "demand":
      return { x: rtl ? 50 : 50, y: 12 };
    case "suppliers":
      return { x: rtl ? 78 : 22, y: 36 };
    case "sales":
      return { x: rtl ? 22 : 78, y: 36 };
    case "inventory":
      return { x: rtl ? 72 : 28, y: 86 };
    case "cost":
      return { x: rtl ? 28 : 72, y: 86 };
    default:
      return p;
  }
}

const EDGES_FALLBACK: { a: NodeId; b: NodeId }[] = [
  { a: "nazmos", b: "demand" },
  { a: "nazmos", b: "suppliers" },
  { a: "nazmos", b: "sales" },
  { a: "nazmos", b: "inventory" },
  { a: "nazmos", b: "cost" },
];