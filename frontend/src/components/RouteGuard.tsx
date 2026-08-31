"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Capabilities, hasCapability } from "@/lib/auth";
import { useAuthStore } from "@/stores/authStore";

interface RouteGuardProps {
  children: React.ReactNode;
  /** Redirect unauthenticated visitors here. */
  redirectTo?: string;
  /** When set, requires this capability or redirects to `redirectOnDenied`. */
  require?: keyof Capabilities;
  /** Where to send authenticated users who lack the required capability. */
  redirectOnDenied?: string;
}

/**
 * Single enforcement point for route-level access.
 *
 * Authentication comes from the auth store (populated by /auth/me, which the
 * backend computes server-side). Capability checks use the SAME object the
 * backend re-checks on every request — the frontend renders the server's
 * answer and never decides permissions itself.
 */
export default function RouteGuard({
  children,
  redirectTo = "/login",
  require,
  redirectOnDenied = "/dashboard",
}: RouteGuardProps) {
  const { isAuthenticated, isLoading, capabilities } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace(redirectTo);
      return;
    }
    if (require && !hasCapability(capabilities, require)) {
      router.replace(redirectOnDenied);
    }
  }, [isLoading, isAuthenticated, capabilities, require, redirectTo, redirectOnDenied, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  if (require && !hasCapability(capabilities, require)) {
    return null;
  }

  return <>{children}</>;
}
