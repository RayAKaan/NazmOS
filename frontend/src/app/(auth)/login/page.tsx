"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Toast } from "@/components/ui/Toast";
import { useI18n } from "@/lib/i18n";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import api from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loginSchema = useMemo(
    () =>
      z.object({
        email: z.string().email(t.auth.login.emailError),
        password: z.string().min(8, t.auth.login.passwordError),
      }),
    [t.auth.login.emailError, t.auth.login.passwordError]
  );

  type LoginForm = z.infer<typeof loginSchema>;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginForm) => {
    setIsSubmitting(true);
    try {
      await api.post("/auth/login", data);
      router.push("/dashboard");
    } catch (error: any) {
      setToast({
        message: error.response?.data?.message || t.auth.login.error,
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDemoLogin = () => {
    router.push("/demo");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4 relative">
      <div className="absolute top-4 right-4 z-10">
        <LanguageSwitcher />
      </div>

      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-bold text-3xl">N</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">{t.auth.login.title}</h1>
          <p className="text-text-muted mt-2">{t.auth.login.subtitle}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            label={t.auth.login.email}
            type="email"
            placeholder={t.auth.login.emailPlaceholder}
            error={errors.email?.message}
            {...register("email")}
          />
          <Input
            label={t.auth.login.password}
            type="password"
            placeholder={t.auth.login.passwordPlaceholder}
            error={errors.password?.message}
            {...register("password")}
          />
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? t.auth.login.signingIn : t.auth.login.signIn}
          </Button>
        </form>

        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="px-2 bg-bg-primary text-text-muted">{t.auth.login.or}</span>
            </div>
          </div>

          <Button
            variant="secondary"
            className="w-full mt-4"
            onClick={handleDemoLogin}
          >
            {t.auth.login.tryDemo}
          </Button>
        </div>

        <p className="text-center text-text-muted mt-6">
          {t.auth.login.noAccount}{" "}
          <Link href="/register" className="text-blue-400 hover:underline">
            {t.auth.login.register}
          </Link>
        </p>
      </div>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}
