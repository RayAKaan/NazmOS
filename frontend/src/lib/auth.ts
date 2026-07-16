import api from "./api";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone?: string | null;
  role: string;
  is_active?: boolean;
  last_login?: string | null;
  created_at?: string;
}

export interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

export function setAuthTokens(accessToken: string, refreshToken: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem("access_token", accessToken);
  localStorage.setItem("refresh_token", refreshToken);
}

export function clearAuthTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export function isAuthenticated() {
  if (typeof window === "undefined") return false;
  return Boolean(localStorage.getItem("access_token"));
}

export const authApi = {
  async login(email: string, password: string): Promise<AuthResponse> {
    const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
    return data;
  },

  async register(email: string, password: string, fullName: string, phone?: string): Promise<AuthResponse> {
    const { data } = await api.post<AuthResponse>("/auth/register", {
      email,
      password,
      full_name: fullName,
      phone: phone || null,
    });
    return data;
  },

  async loginDemo(): Promise<AuthResponse> {
    return {
      access_token: "demo-token",
      refresh_token: "demo-refresh-token",
      user: {
        id: "demo-user-001",
        email: "demo@nazmos.sa",
        full_name: "Demo User",
        role: "owner",
        is_active: true,
      },
    };
  },

  async getMe(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },
};
