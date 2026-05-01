"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { registerSchema, type RegisterInput } from "@/lib/validators/auth";
import { useRegister } from "@/hooks/useRegister";
import { getApiErrorMessage } from "@/lib/errors";

export default function RegisterPage() {
  const {
    register: field,  // renamed to avoid clash with our hook below
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
  });

  const registerUser = useRegister();

  const onSubmit = (data: RegisterInput) => registerUser.mutate(data);

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6 rounded-lg border border-gray-200 p-8">
        <h1 className="text-2xl font-semibold">Create your account</h1>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Name */}
          <div>
            <label htmlFor="name" className="block text-sm font-medium">
              Name
            </label>
            <input
              id="name"
              type="text"
              autoComplete="name"
              {...field("name")}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 outline-none focus:border-blue-500"
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>
            )}
          </div>

          {/* Email */}
          <div>
            <label htmlFor="email" className="block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              {...field("email")}
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
              autoComplete="new-password"
              {...field("password")}
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 outline-none focus:border-blue-500"
            />
            {errors.password && (
              <p className="mt-1 text-sm text-red-600">
                {errors.password.message}
              </p>
            )}
          </div>

          {/* Server error */}
          {registerUser.error && (
            <p className="rounded bg-red-50 p-2 text-sm text-red-700">
              {getApiErrorMessage(registerUser.error)}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={registerUser.isPending}
            className="w-full rounded bg-blue-600 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {registerUser.isPending ? "Creating account..." : "Sign up"}
          </button>
        </form>

        <p className="text-center text-sm text-gray-600">
          Already have an account?{" "}
          <Link href="/login" className="text-blue-600 hover:underline">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}