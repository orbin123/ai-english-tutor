"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { loginSchema, type LoginInput } from "@/lib/validators/auth";
import { useLogin } from "@/hooks/useLogin";
import { getApiErrorMessage } from "@/lib/errors";

export default function LoginPage() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
  });

  const login = useLogin();

  const onSubmit = (data: LoginInput) => login.mutate(data);

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6 rounded-lg border border-gray-200 p-8">
        <h1 className="text-2xl font-semibold">Log in</h1>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Email */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              {...register("email")}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 outline-none focus:border-blue-500"
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
            )}
          </div>

          {/* Password */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 outline-none focus:border-blue-500"
            />
            {errors.password && (
              <p className="mt-1 text-sm text-red-600">
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Server error */}
          {login.error && (
            <p className="rounded bg-red-50 p-2 text-sm text-red-700">
              {getApiErrorMessage(login.error)}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={login.isPending}
            className="w-full rounded bg-blue-600 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {login.isPending ? "Logging in..." : "Log in"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-600">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-blue-600 hover:underline">
            Register
          </Link>
        </p>
      </div>
    </main>
  );
}