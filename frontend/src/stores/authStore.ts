import { create } from "zustand";
import { Capabilities, EMPTY_CAPABILITIES, User, authApi, clearAuthTokens, isAuthenticated } from "@/lib/auth";

interface AuthState {
  user: User | null;
  capabilities: Capabilities;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, phone?: string) => Promise<void>;
  loginDemo: () => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  capabilities: EMPTY_CAPABILITIES,
  isAuthenticated: isAuthenticated(),
  isLoading: false,

  login: async (email: string, password: string) => {
    set({ isLoading: true });
    try {
      const { user, capabilities } = await authApi.login(email, password);
      set({ user, capabilities, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (email: string, password: string, fullName: string, phone?: string) => {
    set({ isLoading: true });
    try {
      const { user, capabilities } = await authApi.register(email, password, fullName, phone);
      set({ user, capabilities, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginDemo: async () => {
    set({ isLoading: true });
    try {
      const { user, capabilities } = await authApi.loginDemo();
      set({ user, capabilities, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    clearAuthTokens();
    set({ user: null, capabilities: EMPTY_CAPABILITIES, isAuthenticated: false });
  },

  checkAuth: async () => {
    if (!isAuthenticated()) {
      set({ isAuthenticated: false, user: null, capabilities: EMPTY_CAPABILITIES });
      return;
    }

    try {
      const { user, capabilities } = await authApi.getMe();
      set({ user, capabilities, isAuthenticated: true });
    } catch {
      await clearAuthTokens();
      set({ user: null, capabilities: EMPTY_CAPABILITIES, isAuthenticated: false });
    }
  },
}));
