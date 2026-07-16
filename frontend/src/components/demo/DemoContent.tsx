"use client";

import { useDemoEngine } from "@/lib/demo-engine";
import { DemoWelcome } from "@/components/demo/DemoWelcome";
import { DemoPipelineFlow } from "@/components/demo/DemoPipelineFlow";
import { DemoOrchestrator } from "@/components/demo/DemoOrchestrator";
import { DemoInventory } from "@/components/demo/DemoInventory";
import { DemoCTA } from "@/components/demo/DemoCTA";
import { AnimatePresence, motion } from "framer-motion";

// Pilot demo intentionally reduced to 3 commercial workflows:
// 1) POS/compliance workflow preview, 2) inventory risk, 3) WhatsApp approval/action.
const steps = [
  DemoWelcome,
  DemoPipelineFlow,
  DemoInventory,
  DemoOrchestrator,
  DemoCTA,
];

export function DemoContent() {
  const { currentStep } = useDemoEngine();
  const StepComponent = steps[currentStep] || DemoWelcome;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={currentStep}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.3 }}
      >
        <StepComponent />
      </motion.div>
    </AnimatePresence>
  );
}
