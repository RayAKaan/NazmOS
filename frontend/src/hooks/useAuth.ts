import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";

export function useAuth() {
  const { user, isAuthenticated, isLoading, logout, checkAuth, loginDemo } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return {
    user,
    isAuthenticated,
    isLoading,
    logout: () => {
      logout();
      router.push("/login");
    },
    loginDemo: async () => {
      await loginDemo();
      router.push("/dashboard");
    },
  };
}
