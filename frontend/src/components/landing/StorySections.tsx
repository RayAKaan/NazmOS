"use client";

import { Fingerprint, ListChecks, Scaling } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { Section, SectionLabel } from "./section";
import { Reveal } from "./Reveal";
import { FigureHeadline } from "@/components/ui/FigureHeadline";
import { SignatureLoop } from "./viz/SignatureLoop";
import { GraphDiagram } from "./viz/GraphDiagram";
import { AgentPipeline } from "./viz/AgentPipeline";
import { DecisionGate } from "./viz/DecisionGate";
import { OutcomeLoop } from "./viz/OutcomeLoop";
import {
  SAMPLE_GRAPH,
  SAMPLE_FINDINGS,
  SAMPLE_DECISION,
  SAMPLE_OUTCOME,
  SAMPLE_AGENTS,
} from "./viz/types";

function StoryHeader({
  badge,
  title,
  body,
}: {
  badge: string;
  title: string;
  body: string;
}) {
  return (
    <Reveal className="min-w-0">
      <SectionLabel>{badge}</SectionLabel>
      <h2 className="mt-5 max-w-3xl font-serif text-4xl font-black leading-tight tracking-[-0.02em] text-foreground [overflow-wrap:anywhere] md:text-5xl">
        {title}
      </h2>
      <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground [overflow-wrap:anywhere]">{body}</p>
    </Reveal>
  );
}

export function MemorySection() {
  const { t } = useI18n();
  const facts = t.landing.story.memory.facts as {
    label: string;
    value: number;
    suffix?: string;
    tone: "primary" | "secondary" | "success";
  }[];
  const toneMap: Record<string, "gold" | "default" | "success"> = {
    primary: "gold",
    secondary: "default",
    success: "success",
  };
  return (
    <Section className="bg-muted/30">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <StoryHeader
          badge={t.landing.story.memory.badge}
          title={t.landing.story.memory.title}
          body={t.landing.story.memory.body}
        />
        <Reveal delay={0.1} className="min-w-0">
          <div className="grid items-center gap-8 lg:grid-cols-2">
            <div className="min-w-0">
              <SignatureLoop />
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-3">
              {facts.map((f) => (
                <div key={f.label} className="rounded-2xl border border-border bg-card p-4">
                  {f.suffix ? (
                    <FigureHeadline
                      value={f.value}
                      label={f.label}
                      size="secondary"
                      tone={toneMap[f.tone] ?? "default"}
                      className="[&_div]:flex-row [&_div]:items-baseline [&_div]:gap-1 [&_div+span]:hidden"
                    />
                  ) : (
                    <FigureHeadline
                      value={f.value}
                      label={f.label}
                      size="secondary"
                      tone={toneMap[f.tone] ?? "default"}
                      className="[&_div]:flex-row [&_div]:items-baseline [&_div]:gap-1"
                    />
                  )}
                  {f.suffix && <span className="text-sm text-muted-foreground">{f.suffix}</span>}
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

export function GraphSection() {
  const { t } = useI18n();
  return (
    <Section>
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div className="order-2 min-w-0 lg:order-1">
          <Reveal>
            <GraphDiagram
              nodes={SAMPLE_GRAPH.nodes}
              edges={SAMPLE_GRAPH.edges}
              className="h-80"
            />
          </Reveal>
        </div>
        <div className="order-1 min-w-0 lg:order-2">
          <StoryHeader
            badge={t.landing.story.graph.badge}
            title={t.landing.story.graph.title}
            body={t.landing.story.graph.body}
          />
        </div>
      </div>
    </Section>
  );
}

export function AgentsSection() {
  const { t } = useI18n();
  return (
    <Section className="bg-muted/30">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <StoryHeader
          badge={t.landing.story.agents.badge}
          title={t.landing.story.agents.title}
          body={t.landing.story.agents.body}
        />
        <Reveal delay={0.1} className="min-w-0">
          <AgentPipeline agents={SAMPLE_AGENTS} />
        </Reveal>
      </div>
    </Section>
  );
}

export function ReasoningSection() {
  const { t } = useI18n();
  const steps = t.landing.story.reasoning.steps as string[];
  return (
    <Section>
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div className="order-2 min-w-0 lg:order-1">
          <Reveal>
            <div className="rounded-3xl border border-border bg-card p-8 shadow-elevation-2">
              <div className="mb-6 flex items-center gap-3">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
                  <Fingerprint className="h-6 w-6 text-primary" aria-hidden="true" />
                </span>
                <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
                  {t.landing.labels.boundedByEvidence}
                </p>
              </div>
              <ol className="space-y-4">
                {steps.map((s, i) => (
                  <li key={s} className="flex items-start gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-bold text-primary">
                      {i + 1}
                    </span>
                    <span className="pt-1 text-muted-foreground">{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          </Reveal>
        </div>
        <div className="order-1 min-w-0 lg:order-2">
          <StoryHeader
            badge={t.landing.story.reasoning.badge}
            title={t.landing.story.reasoning.title}
            body={t.landing.story.reasoning.body}
          />
        </div>
      </div>
    </Section>
  );
}

export function DecisionSection() {
  const { t } = useI18n();
  return (
    <Section className="bg-muted/30">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <StoryHeader
          badge={t.landing.story.decision.badge}
          title={t.landing.story.decision.title}
          body={t.landing.story.decision.body}
        />
        <Reveal delay={0.1} className="min-w-0">
          <DecisionGate decision={SAMPLE_DECISION} />
          <div className="mt-4 flex items-center gap-2 pl-2 text-sm text-muted-foreground">
            <ListChecks className="h-4 w-4 text-primary" aria-hidden="true" />
            {t.landing.story.loopNote}
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

export function OutcomeSection() {
  const { t } = useI18n();
  return (
    <Section>
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div className="order-2 min-w-0 lg:order-1">
          <Reveal>
            <OutcomeLoop outcome={SAMPLE_OUTCOME} />
          </Reveal>
        </div>
        <div className="order-1 min-w-0 lg:order-2">
          <StoryHeader
            badge={t.landing.story.outcome.badge}
            title={t.landing.story.outcome.title}
            body={t.landing.story.outcome.body}
          />
          <div className="mt-6">
            <Reveal delay={0.15}>
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <Scaling className="h-4 w-4 text-success" aria-hidden="true" />
                {t.landing.story.loopNote}
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </Section>
  );
}
