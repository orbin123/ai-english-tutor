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
    mutationFn: async (data: LoginInput) => {
      const token = await authApi.login(data);
      // Save token first, then fetch /me with it
      setToken(token.access_token);
      const me = await authApi.me();
      return me;
    },
    onSuccess: (me) => {
      router.push(me.diagnosis_completed ? "/dashboard" : "/diagnosis");
    },
  });
}