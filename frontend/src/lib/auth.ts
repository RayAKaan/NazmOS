import api from "./api";
import { SESSION_COOKIE } from "./session";

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

async function establishSession(tokens: { access_token: string; refresh_token: string }) {
  const res = await fetch("/api/auth/set-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tokens),
  });
  if (!res.ok) {
    throw new Error("Failed to establish session");
  }
}

export async function clearAuthTokens() {
  if (typeof window === "undefined") return;
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
}

export function isAuthenticated() {
  if (typeof window === "undefined") return false;
  return document.cookie.split("; ").some((c) => c.startsWith(`${SESSION_COOKIE}=1`));
}

export const authApi = {
  async login(email: string, password: string): Promise<{ user: User }> {
    const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
    await establishSession(data);
    return { user: data.user };
  },

  async register(
    email: string,
    password: string,
    fullName: string,
    phone?: string
  ): Promise<{ user: User }> {
    const { data } = await api.post<AuthResponse>("/auth/register", {
      email,
      password,
      full_name: fullName,
      phone: phone || null,
    });
    await establishSession(data);
    return { user: data.user };
  },

  async loginDemo(): Promise<{ user: User }> {
    return {
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
