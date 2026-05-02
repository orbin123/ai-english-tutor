"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { loginSchema, type LoginInput } from "@/lib/validators/auth";
import { useLogin } from "@/hooks/useLogin";
import { useRedirectIfAuthed } from "@/hooks/useRedirectIfAuthed";
import { getApiErrorMessage } from "@/lib/errors";

import { AuthCard } from "@/components/auth/AuthCard";
import { FormField } from "@/components/auth/FormField";
import { SubmitButton } from "@/components/auth/SubmitButton";
import { ServerErrorBanner } from "@/components/auth/ServerErrorBanner";
import {
  SocialDivider,
  GoogleButton,
} from "@/components/auth/SocialDivider";

// Map query param error codes to user-friendly messages
const OAUTH_ERRORS: Record<string, string> = {
  google_failed: "Google sign-in failed. Please try again or use email and password.",
};

export default function LoginPage() {
  const searchParams = useSearchParams();
  const oauthError = searchParams.get("error");
  const oauthErrorMessage = oauthError ? (OAUTH_ERRORS[oauthError] ?? "Sign-in failed. Please try again.") : null;
  useRedirectIfAuthed();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
  });

  const login = useLogin();

  const onSubmit = (data: LoginInput) => login.mutate(data);

  const serverError = login.error ? getApiErrorMessage(login.error) : (oauthErrorMessage ?? null);

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Log in to continue your coaching session"
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="font-semibold hover:underline"
            style={{ color: "oklch(52% 0.18 240)" }}
          >
            Sign up
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ServerErrorBanner message={serverError} />

        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...register("email")}
        />

        <FormField
          label="Password"
          type="password"
          autoComplete="current-password"
          placeholder="Enter your password"
          error={errors.password?.message}
          rightSlot={
            <Link
              href="/forgot-password"
              className="text-[12.5px] font-medium hover:underline"
              style={{ color: "oklch(52% 0.18 240)" }}
            >
              Forgot password?
            </Link>
          }
          {...register("password")}
        />

        <div className="mt-6">
          <SubmitButton loading={login.isPending} loadingText="Logging in...">
            Log in
          </SubmitButton>
        </div>

        <SocialDivider />
        <GoogleButton />
      </form>
    </AuthCard>
  );
}