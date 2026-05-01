"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/auth-api";
import { useAuthStore } from "@/store/authStore";
import type { RegisterInput } from "@/lib/validators/auth";

export function useRegister() {
  const router = useRouter();
  const setToken = useAuthStore((s) => s.setToken);

  return useMutation({
    // Auto-login: signup, then immediately login with same credentials
    mutationFn: async (data: RegisterInput) => {
      await authApi.signup(data);
      return authApi.login({ email: data.email, password: data.password });
    },
    onSuccess: (res) => {
      setToken(res.access_token);
      // New users always need diagnosis
      router.push("/diagnosis");
    },
  });
}