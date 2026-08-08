import axios from "axios";

// Same-origin BFF: the browser only ever talks to the Next.js server, which
// injects the Bearer token from the httpOnly cookie (see src/middleware.ts).
const api = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

function redirectToLogin() {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
  }
}

async function clearSession() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const isAuthEndpoint =
      original?.url?.includes("/auth/login") ||
      original?.url?.includes("/auth/register") ||
      original?.url?.includes("/auth/refresh");

    if (error.response?.status === 401 && original && !(original as any)._retried && !isAuthEndpoint) {
      (original as any)._retried = true;
      try {
        const res = await fetch("/api/auth/refresh", { method: "POST" });
        if (!res.ok) {
          await clearSession();
          redirectToLogin();
          return Promise.reject(error);
        }
        return api(original);
      } catch (refreshError) {
        await clearSession();
        redirectToLogin();
        return Promise.reject(refreshError);
      }
    }

    if (error.response?.status === 401) {
      await clearSession();
      redirectToLogin();
    }
    return Promise.reject(error);
  }
);

export default api;
