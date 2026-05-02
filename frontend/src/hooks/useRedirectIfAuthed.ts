"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

/**
 * useRedirectIfAuthed
 *
 * Use this on auth pages (login, register).
 * If the user is already logged in, send them to /dashboard.
 *
 * This prevents a logged-in user from seeing the login form.
 */
export function useRedirectIfAuthed() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hydrated = useAuthStore((s) => s._hydrated);

  useEffect(() => {
    if (!hydrated) return;
    if (isAuthenticated) {
      router.replace("/dashboard");
    }
  }, [hydrated, isAuthenticated, router]);
}
