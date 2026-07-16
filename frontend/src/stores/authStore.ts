import { create } from "zustand";
import { User, authApi, setAuthTokens, clearAuthTokens, isAuthenticated } from "@/lib/auth";

interface AuthState {
  user: User | null;
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
  isAuthenticated: isAuthenticated(),
  isLoading: false,

  login: async (email: string, password: string) => {
    set({ isLoading: true });
    try {
      const response = await authApi.login(email, password);
      setAuthTokens(response.access_token, response.refresh_token);
      set({ user: response.user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (email: string, password: string, fullName: string, phone?: string) => {
    set({ isLoading: true });
    try {
      const response = await authApi.register(email, password, fullName, phone);
      setAuthTokens(response.access_token, response.refresh_token);
      set({ user: response.user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginDemo: async () => {
    set({ isLoading: true });
    try {
      const response = await authApi.loginDemo();
      setAuthTokens(response.access_token, response.refresh_token);
      set({ user: response.user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: () => {
    clearAuthTokens();
    set({ user: null, isAuthenticated: false });
  },

  checkAuth: async () => {
    if (!isAuthenticated()) {
      set({ isAuthenticated: false, user: null });
      return;
    }

    // Demo token — use mock user without hitting backend
    if (localStorage.getItem("access_token") === "demo-token") {
      set({
        user: {
          id: "demo-user-001",
          email: "demo@nazmos.sa",
          full_name: "Demo User",
          role: "owner",
        },
        isAuthenticated: true,
      });
      return;
    }

    try {
      const user = await authApi.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      clearAuthTokens();
      set({ user: null, isAuthenticated: false });
    }
  },
}));
