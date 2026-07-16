import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DemoState {
  showWelcome: boolean;
  setShowWelcome: (show: boolean) => void;
  
  tourActive: boolean;
  tourStep: number;
  tourCompleted: boolean;
  startTour: () => void;
  nextTourStep: () => void;
  prevTourStep: () => void;
  endTour: () => void;
  setTourCompleted: (completed: boolean) => void;
  
  actionsCompleted: string[];
  addActionCompleted: (action: string) => void;
  
  showSignupPrompt: boolean;
  setShowSignupPrompt: (show: boolean) => void;
}

export const useDemoStore = create<DemoState>()(
  persist(
    (set, get) => ({
      showWelcome: true,
      setShowWelcome: (show) => set({ showWelcome: show }),
      
      tourActive: false,
      tourStep: 0,
      tourCompleted: false,
      startTour: () => set({ tourActive: true, tourStep: 0 }),
      nextTourStep: () => {
        const currentStep = get().tourStep;
        if (currentStep < 4) {
          set({ tourStep: currentStep + 1 });
        } else {
          set({ tourActive: false, tourCompleted: true });
        }
      },
      prevTourStep: () => {
        const currentStep = get().tourStep;
        if (currentStep > 0) {
          set({ tourStep: currentStep - 1 });
        }
      },
      endTour: () => set({ tourActive: false }),
      setTourCompleted: (completed) => set({ tourCompleted: completed }),
      
      actionsCompleted: [],
      addActionCompleted: (action) => 
        set((state) => ({
          actionsCompleted: [...state.actionsCompleted, action],
        })),
      
      showSignupPrompt: false,
      setShowSignupPrompt: (show) => set({ showSignupPrompt: show }),
    }),
    {
      name: 'nazmos-demo-storage',
      partialize: (state) => ({
        tourCompleted: state.tourCompleted,
        actionsCompleted: state.actionsCompleted,
      }),
    }
  )
);
