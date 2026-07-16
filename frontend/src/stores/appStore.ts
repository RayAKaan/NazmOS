import { create } from "zustand";

interface AppState {
  businessId: string | null;
  setBusinessId: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  businessId: null,
  setBusinessId: (id) => set({ businessId: id }),
}));
