import api from "./api";
import { SESSION_COOKIE } from "./session";

/**
 * Server-declared capabilities returned by /auth/me and login/register.
 * Mirrors app/services/capabilities_service.py. The frontend renders from
 * this object and never independently decides permissions.
 */
export interface Capabilities {
  is_platform_operator: boolean;
  can_view_ops_console: boolean;
  can_run_admin_tools: boolean;
  can_manage_team: boolean;
  can_run_orchestrator: boolean;
  can_approve_actions: boolean;
  role: string | null;
  business_id: string | null;
}

export const EMPTY_CAPABILITIES: Capabilities = {
  is_platform_operator: false,
  can_view_ops_console: false,
  can_run_admin_tools: false,
  can_manage_team: false,
  can_run_orchestrator: false,
  can_approve_actions: false,
  role: null,
  business_id: null,
};

export function hasCapability(
  capabilities: Capabilities | null | undefined,
  capability: keyof Capabilities
): boolean {
  return Boolean(capabilities && capabilities[capability]);
}

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
  capabilities?: Capabilities | null;
}

export interface MeResponse {
  user: User;
  capabilities: Capabilities;
  business_id: string | null;
  role: string | null;
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
  async login(email: string, password: string): Promise<{ user: User; capabilities: Capabilities }> {
    const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
    await establishSession(data);
    return { user: data.user, capabilities: data.capabilities || EMPTY_CAPABILITIES };
  },

  async register(
    email: string,
    password: string,
    fullName: string,
    phone?: string
  ): Promise<{ user: User; capabilities: Capabilities }> {
    const { data } = await api.post<AuthResponse>("/auth/register", {
      email,
      password,
      full_name: fullName,
      phone: phone || null,
    });
    await establishSession(data);
    return { user: data.user, capabilities: data.capabilities || EMPTY_CAPABILITIES };
  },

  async loginDemo(): Promise<{ user: User; capabilities: Capabilities }> {
    return {
      user: {
        id: "demo-user-001",
        email: "demo@nazmos.sa",
        full_name: "Demo User",
        role: "owner",
        is_active: true,
      },
      capabilities: {
        ...EMPTY_CAPABILITIES,
        role: "owner",
        can_manage_team: true,
        can_run_orchestrator: true,
        can_approve_actions: true,
      },
    };
  },

  async getMe(): Promise<{ user: User; capabilities: Capabilities }> {
    const { data } = await api.get<MeResponse>("/auth/me");
    return { user: data.user, capabilities: data.capabilities || EMPTY_CAPABILITIES };
  },
};
