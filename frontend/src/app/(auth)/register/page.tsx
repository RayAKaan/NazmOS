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
import { useAuthStore } from "@/stores/authStore";

export default function RegisterPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const registerSchema = useMemo(
    () =>
      z.object({
        fullName: z.string().min(2, t.auth.register.nameError),
        email: z.string().email(t.auth.register.emailError),
        password: z.string().min(8, t.auth.register.passwordError),
        phone: z.string().optional(),
      }),
    [t.auth.register.nameError, t.auth.register.emailError, t.auth.register.passwordError]
  );

  type RegisterForm = z.infer<typeof registerSchema>;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterForm) => {
    setIsSubmitting(true);
    try {
      await useAuthStore.getState().register(
        data.email,
        data.password,
        data.fullName,
        data.phone
      );
      router.push("/onboarding");
    } catch (error: any) {
      setToast({
        message:
          error.response?.data?.detail ||
          error.response?.data?.message ||
          t.auth.register.error,
        type: "error",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4 relative">
      <div className="absolute top-4 right-4 z-10">
        <LanguageSwitcher />
      </div>

      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center mx-auto mb-4">
            <span className="text-primary-foreground font-bold text-3xl">N</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">{t.auth.register.title}</h1>
          <p className="text-text-muted mt-2">{t.auth.register.subtitle}</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            label={t.auth.register.fullName}
            type="text"
            placeholder={t.auth.register.fullNamePlaceholder}
            error={errors.fullName?.message}
            {...register("fullName")}
          />
          <Input
            label={t.auth.register.email}
            type="email"
            placeholder={t.auth.register.emailPlaceholder}
            error={errors.email?.message}
            {...register("email")}
          />
          <Input
            label={t.auth.register.password}
            type="password"
            placeholder={t.auth.register.passwordPlaceholder}
            error={errors.password?.message}
            {...register("password")}
          />
          <Input
            label={t.auth.register.phone}
            type="tel"
            placeholder={t.auth.register.phonePlaceholder}
            error={errors.phone?.message}
            {...register("phone")}
          />
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? t.auth.register.creating : t.auth.register.createAccount}
          </Button>
        </form>

        <p className="text-center text-text-muted mt-6">
          {t.auth.register.hasAccount}{" "}
          <Link href="/login" className="text-primary hover:underline">
            {t.auth.register.signIn}
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
