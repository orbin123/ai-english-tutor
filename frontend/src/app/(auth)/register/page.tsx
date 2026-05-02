"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";

import { registerSchema, type RegisterInput } from "@/lib/validators/auth";
import { useRegister } from "@/hooks/useRegister";
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

export default function RegisterPage() {
  const {
    register: field,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
  });

  const registerUser = useRegister();
  useRedirectIfAuthed();

  const onSubmit = (data: RegisterInput) => registerUser.mutate(data);

  const serverError = registerUser.error ? getApiErrorMessage(registerUser.error) : null;

  return (
    <AuthCard
      title="Create your account"
      subtitle="Start your personalized English coaching today"
      footer={
        <>
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-semibold hover:underline"
            style={{ color: "oklch(52% 0.18 240)" }}
          >
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <ServerErrorBanner message={serverError} />

        <FormField
          label="Name"
          type="text"
          autoComplete="name"
          placeholder="Your full name"
          error={errors.name?.message}
          {...field("name")}
        />

        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          error={errors.email?.message}
          {...field("email")}
        />

        <FormField
          label="Password"
          type="password"
          autoComplete="new-password"
          placeholder="Create a password"
          error={errors.password?.message}
          hint="At least 8 characters"
          {...field("password")}
        />

        <div className="mt-6">
          <SubmitButton loading={registerUser.isPending} loadingText="Creating account...">
            Create account
          </SubmitButton>
        </div>

        <SocialDivider />
        <GoogleButton />
      </form>
    </AuthCard>
  );
}