import { create } from "zustand";

interface OrbitState {
  selectedAuditId: string | null;
  setSelectedAuditId: (id: string | null) => void;
}

export const useOrbitStore = create<OrbitState>((set) => ({
  selectedAuditId: null,
  setSelectedAuditId: (id) => set({ selectedAuditId: id }),
}));