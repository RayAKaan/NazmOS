'use client';

import * as React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { TrendingUp, Package, Percent, Bell } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/lib/i18n';

function FeatureContent({ feature }: { feature: any }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
      className="h-full"
    >
      <div className="grid grid-cols-2 gap-4 mb-6">
        {feature.stats.map((stat: any, i: number) => (
          <div key={i} className="bg-bg-tertiary border border-border-primary p-4">
            <span className="font-mono text-3xl text-text-primary block">{stat.value}</span>
            <span className="font-sans text-xs text-text-muted uppercase tracking-wider">{stat.label}</span>
          </div>
        ))}
      </div>

      <div className="bg-bg-tertiary border border-border-primary p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="flex -space-x-1">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className={cn(
                  'w-6 h-6 border border-bg-primary',
                  i === 1 ? 'bg-accent-primary' : 'bg-bg-secondary'
                )}
              />
            ))}
          </div>
          <span className="font-sans text-xs text-text-muted">{feature.activeStores}</span>
        </div>
        <p className="font-sans text-sm text-text-secondary">
          {feature.joinText}
        </p>
      </div>
    </motion.div>
  );
}

export function FeaturesBento() {
  const [activeTab, setActiveTab] = React.useState(0);
  const { t } = useI18n();

  const iconMap = [TrendingUp, Package, Percent, Bell];
  const features = t.features.list.map((f: any, i: number) => ({
    ...f,
    icon: iconMap[i],
  }));

  const activeFeature = features[activeTab];

  return (
    <section id="features" className="py-24 bg-bg-primary">
      <div className="container mx-auto px-6">
        <div className="max-w-2xl mb-16">
          <span className="font-mono text-xs text-accent-primary uppercase tracking-widest mb-4 block">
            {t.features.badge}
          </span>
          <h2 className="font-serif text-4xl md:text-5xl font-normal tracking-tight text-text-primary mb-4">
            {t.features.title}
          </h2>
          <p className="font-sans text-lg text-text-secondary">
            {t.features.subtitle}
          </p>
        </div>

        <div className="flex flex-col lg:flex-row gap-8">
          <div className="lg:w-80 flex-shrink-0">
            <div className="flex flex-col gap-1">
              {features.map((feature: any, index: number) => (
                <button
                  key={feature.id}
                  onClick={() => setActiveTab(index)}
                  className={cn(
                    'flex items-center gap-4 p-4 text-left transition-all duration-300 border',
                    activeTab === index
                      ? 'bg-bg-secondary border-accent-primary text-text-primary'
                      : 'bg-transparent border-transparent text-text-secondary hover:text-text-primary hover:bg-bg-secondary'
                  )}
                >
                  <div className="w-10 h-10 flex items-center justify-center border border-border-primary">
                    <feature.icon className="w-5 h-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-sans text-sm font-medium">{feature.label}</span>
                      {feature.badge && (
                        <span className="px-2 py-0.5 bg-status-success/20 text-status-success text-[10px] font-mono uppercase">
                          {feature.badge}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 bg-bg-secondary border border-border-primary p-8 min-h-[400px]">
            <div className="mb-8">
              <h3 className="font-serif text-3xl text-text-primary mb-2">{activeFeature.header}</h3>
              <p className="font-sans text-text-secondary">{activeFeature.description}</p>
            </div>

            <AnimatePresence mode="wait">
              <FeatureContent key={activeFeature.id} feature={activeFeature} />
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}
