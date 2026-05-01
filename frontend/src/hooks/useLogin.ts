"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/auth-api";
import { useAuthStore } from "@/store/authStore";
import type { LoginInput } from "@/lib/validators/auth";

export function useLogin() {
  const router = useRouter();
  const setToken = useAuthStore((s) => s.setToken);

  return useMutation({
    mutationFn: (data: LoginInput) => authApi.login(data),
    onSuccess: (res) => {
      setToken(res.access_token);  // saves to localStorage + store
      router.push("/dashboard");
    },
  });
}