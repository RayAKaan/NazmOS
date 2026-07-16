"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { MobileNav } from "@/components/layout/MobileNav";
import { MerchantHelpWidget } from "@/components/free/MerchantHelpWidget";
import { useAuth } from "@/hooks/useAuth";
import { useAppStore } from "@/stores/appStore";
import api from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const { businessId, setBusinessId } = useAppStore();
  const router = useRouter();

  useEffect(() => {
    const initBusiness = async () => {
      if (!isAuthenticated || businessId) return;
      try {
        const response = await api.post("/businesses/bootstrap", {
          name: "My Store",
          type: "baqala",
          city: "Riyadh",
        });
        if (response.data?.id) {
          setBusinessId(response.data.id);
        }
      } catch (error) {
        console.error("Failed to initialize business", error);
      }
    };
    initBusiness();
  }, [isAuthenticated, businessId, setBusinessId]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-accent-blue animate-pulse" />
          <p className="text-text-muted">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="md:ml-60 pb-20 md:pb-0">
        <Header />
        <main className="p-4 md:p-6">{children}</main>
      </div>
      <MerchantHelpWidget />
      <MobileNav />
    </div>
  );
}
