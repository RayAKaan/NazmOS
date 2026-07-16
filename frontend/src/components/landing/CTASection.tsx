"use client";

import { RevealOnScroll } from "./RevealOnScroll";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";

export function CTASection() {
  const { t } = useI18n();

  return (
    <section className="py-24 px-4 bg-background relative border-t border-border">
      <div className="container mx-auto max-w-4xl">
        <RevealOnScroll>
          <div className="text-center">
            <h2 className="font-serif text-4xl md:text-5xl lg:text-6xl font-normal mb-6 text-foreground">
              {t.cta.title}
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10">
              {t.cta.subtitle}
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/demo">
                <Button size="lg">
                  {t.cta.startFree}
                </Button>
              </Link>
            </div>

            <p className="mt-6 text-sm text-muted">
              {t.cta.noCreditCard}
            </p>
          </div>
        </RevealOnScroll>
      </div>
    </section>
  );
}
