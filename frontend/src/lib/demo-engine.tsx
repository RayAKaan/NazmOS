"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface DemoEngineContextValue {
  currentStep: number;
  totalSteps: number;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  resetDemo: () => void;
}

const TOTAL_DEMO_STEPS = 5;
const DemoEngineContext = createContext<DemoEngineContextValue | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [currentStep, setCurrentStep] = useState(0);

  const value = useMemo<DemoEngineContextValue>(() => ({
    currentStep,
    totalSteps: TOTAL_DEMO_STEPS,
    nextStep: () => setCurrentStep((step) => Math.min(step + 1, TOTAL_DEMO_STEPS - 1)),
    prevStep: () => setCurrentStep((step) => Math.max(step - 1, 0)),
    goToStep: (step: number) => setCurrentStep(Math.max(0, Math.min(step, TOTAL_DEMO_STEPS - 1))),
    resetDemo: () => setCurrentStep(0),
  }), [currentStep]);

  return (
    <DemoEngineContext.Provider value={value}>
      {children}
    </DemoEngineContext.Provider>
  );
}

export function useDemoEngine() {
  const ctx = useContext(DemoEngineContext);
  if (!ctx) {
    throw new Error("useDemoEngine must be used within DemoProvider");
  }
  return ctx;
}
