"use client";

import { useState } from "react";
import { BentoGrid } from "@/components/ui/BentoGrid";
import { Card } from "@/components/ui/Card";
import { ChevronDivider } from "@/components/ui/ChevronDivider";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { SeamBorder, type SeamState } from "@/components/ui/SeamBorder";
import { WeaveTile } from "@/components/ui/WeaveTile";
import { ShineBorder } from "@/components/ui/ShineBorder";
import { SplitText } from "@/components/ui/SplitText";
import { Marquee } from "@/components/ui/Marquee";
import { AmbientBackground } from "@/components/ui/AmbientBackground";

/**
 * /ui-kit — reference implementation for the §4 primitives. The page-pass stage (§5)
 * copies FROM here, not from five ad-hoc interpretations.
 * North Star (§0): a private banking terminal engraved with a Najdi weaver's precision.
 */
export default function UiKitPage() {
  const [seam, setSeam] = useState<SeamState>("idle");

  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-12">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-foreground">Primitives — ui-kit</h1>
        <p className="text-sm text-muted-foreground">
          Single reference for Card, FigureHeadline, BentoGrid, ChevronDivider, WeaveTile, SeamBorder.
        </p>
      </header>

      {/* ---------- FigureHeadline ---------- */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-foreground">FigureHeadline</h2>
        <Card density="editorial" trim="weave">
          <div className="space-y-6">
            <FigureHeadline value={128450} currency="SAR" label="Money recovered" trend={{ direction: "up", percent: 12.4 }} />
            <FigureHeadline value={3120} currency="SAR" label="Margin leakage" size="secondary" trend={{ direction: "down", percent: 2.4 }} />
          </div>
        </Card>
      </section>

      {/* ---------- BentoGrid + Card ---------- */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-foreground">BentoGrid + Card</h2>
        <BentoGrid cols={{ base: 1, md: 2, lg: 4 }} gap={6}>
          {["Sales", "Margin", "Dead stock", "Recovery"].map((t) => (
            <Card key={t} density="editorial" hoverable>
              <FigureHeadline value={41200} label={t} size="secondary" />
            </Card>
          ))}
        </BentoGrid>
        <Card density="data" variant="bordered">
          <p className="text-sm text-muted-foreground">Card density=&quot;data&quot; — 16px padding for dense tables.</p>
        </Card>
      </section>

      {/* ---------- ChevronDivider ---------- */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-foreground">ChevronDivider</h2>
        <div className="space-y-2 rounded-lg border border-border bg-card p-6">
          <p className="text-sm text-muted-foreground">Above</p>
          <ChevronDivider />
          <p className="text-sm text-muted-foreground">Below</p>
        </div>
        <div className="flex h-16 items-stretch gap-4 rounded-lg border border-border bg-card p-6">
          <span className="text-sm text-muted-foreground">L</span>
          <ChevronDivider orientation="vertical" />
          <span className="text-sm text-muted-foreground">R</span>
        </div>
      </section>

      {/* ---------- WeaveTile ---------- */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold text-foreground">WeaveTile (field)</h2>
        <div className="relative h-48 overflow-hidden rounded-lg border border-border bg-card">
          <WeaveTile variant="field" />
          <p className="relative z-10 p-8 text-sm text-foreground">
            Full-bleed field at <code>--weave-opacity-bg</code> (0.04 dark / 0.016 light).
            Foreground copy stays AA over the motif.
          </p>
        </div>
      </section>

      {/* ---------- SeamBorder ---------- */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-foreground">SeamBorder (kintsugi)</h2>
          <button
            onClick={() => setSeam((s) => (s === "idle" ? "resolving" : s === "resolving" ? "recovered" : "idle"))}
            className="rounded-md border border-border bg-muted px-4 py-2 text-sm text-foreground"
          >
            Cycle: {seam}
          </button>
        </div>
        <SeamBorder state={seam}>
          <div className="p-6">
            <FigureHeadline value={8400} currency="SAR" label="Recovered value" size="secondary" />
            <p className="mt-2 text-sm text-muted-foreground">
              resolving → recovered draws the gold seam once (600ms). Money Audit &amp; Recovery Match only.
            </p>
          </div>
        </SeamBorder>
      </section>

      {/* ---------- v3 polish: elevation, count-up, shine, split-text, marquee, ambient ---------- */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-foreground">v3 polish — elevation &amp; motion</h2>

        <div className="grid gap-6 md:grid-cols-2">
          <Card density="editorial">
            <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">level-1 (standard)</p>
            <p className="text-sm text-muted-foreground">Flat 1px shadow + border. Data-dense screens.</p>
          </Card>
          <Card density="editorial" trim="weave">
            <p className="mb-2 text-xs uppercase tracking-widest text-muted-foreground">level-2 (KPI / hero)</p>
            <FigureHeadline value={128450} currency="SAR" label="Counts up on mount" size="secondary" />
          </Card>
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <ShineBorder className="rounded-lg">
            <button className="rounded-lg bg-primary px-6 py-3 font-bold text-primary-foreground">
              Primary CTA — gold beam
            </button>
          </ShineBorder>
          <button className="rounded-lg border border-border bg-muted px-6 py-3 text-sm text-foreground">
            Secondary — no beam
          </button>
        </div>

        <h3 className="text-3xl font-bold tracking-[-0.03em] text-foreground">
          <SplitText text="Numbers read like headlines now." />
        </h3>

        <div className="overflow-hidden rounded-lg border border-border">
          <Marquee speed={24} gap={48}>
            {["Manara", "Souq Al-Watan", "Nakhla", "Joud", "Sahari", "Al-Faisal"].map((n) => (
              <span key={n} className="whitespace-nowrap text-lg font-bold text-muted-foreground">{n}</span>
            ))}
          </Marquee>
        </div>

        <div className="relative h-40 overflow-hidden rounded-lg border border-border bg-card grain">
          <AmbientBackground />
          <p className="relative z-10 p-6 text-sm text-foreground">AmbientBackground — brand-forward screens only.</p>
        </div>
      </section>
    </main>
  );
}
