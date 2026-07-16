'use client';

import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { Package, TrendingUp, Bell, ShoppingCart, BarChart3 } from 'lucide-react';
import { useI18n } from '@/lib/i18n';

function StoryItem({ item, index }: { item: any; index: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start end', 'end start'],
  });

  const opacity = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [0.3, 1, 1, 0.3]);
  const y = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [50, 0, 0, -50]);

  const isEven = index % 2 === 0;
  const Icon = item.icon;

  return (
    <motion.div
      ref={ref}
      style={{ opacity, y }}
      className={`py-24 ${isEven ? '' : 'bg-bg-secondary'}`}
    >
      <div className="container mx-auto px-6">
        <div className={`grid md:grid-cols-2 gap-12 items-center ${isEven ? '' : 'md:flex-row-reverse'}`}>
          <div className={isEven ? '' : 'md:order-2'}>
            <div className="flex items-center gap-4 mb-6">
              <div className="w-12 h-12 flex items-center justify-center border border-border-primary bg-bg-tertiary">
                <Icon className="w-5 h-5 text-accent-primary" />
              </div>
              <span className="font-mono text-sm text-accent-primary">{item.number}</span>
            </div>
            
            <h3 className="font-serif text-3xl md:text-4xl lg:text-5xl font-normal tracking-tight text-text-primary mb-6">
              {item.title}
            </h3>
            
            <p className="font-sans text-lg text-text-secondary leading-relaxed max-w-lg">
              {item.description}
            </p>
          </div>
          
          <div className={`${isEven ? '' : 'md:order-1'}`}>
            <div className="aspect-[4/3] bg-bg-tertiary border border-border-primary relative overflow-hidden">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-32 h-32 border border-border-primary bg-bg-secondary flex items-center justify-center">
                  <Icon className="w-16 h-16 text-accent-primary/20" />
                </div>
              </div>
              <div className="absolute top-4 left-4 w-24 h-16 bg-bg-secondary border border-border-primary" />
              <div className="absolute bottom-4 right-4 w-32 h-20 bg-bg-secondary border border-border-primary" />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function StorySection() {
  const { t } = useI18n();

  const iconMap = [Package, TrendingUp, Bell, ShoppingCart, BarChart3];
  const storyItems = t.story.items.map((item: any, i: number) => ({
    ...item,
    icon: iconMap[i],
  }));

  return (
    <section id="story" className="relative">
      <div className="py-24 bg-bg-primary text-center border-y border-border-primary">
        <div className="container mx-auto px-6">
          <span className="font-mono text-xs text-accent-primary uppercase tracking-widest mb-4 block">
            {t.story.badge}
          </span>
          <h2 className="font-serif text-4xl md:text-5xl lg:text-6xl font-normal tracking-tight text-text-primary mb-6">
            {t.story.title}
          </h2>
          <p className="font-sans text-lg text-text-secondary max-w-2xl mx-auto">
            {t.story.subtitle}
          </p>
        </div>
      </div>
      
      {storyItems.map((item: any, index: number) => (
        <StoryItem key={item.id} item={item} index={index} />
      ))}
    </section>
  );
}
