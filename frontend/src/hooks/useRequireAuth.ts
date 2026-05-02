"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

/**
 * useRequireAuth
 *
 * Use this at the top of every protected page.
 *
 * What it does:
 *  - Waits for the auth store to finish reading from localStorage (_hydrated).
 *  - If the user has no token after hydration → redirects to /login.
 *  - Returns { isReady } so the page knows when it's safe to render.
 *
 * Usage:
 *   const { isReady } = useRequireAuth();
 *   if (!isReady) return null;   // or a loading spinner
 */
export function useRequireAuth() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hydrated = useAuthStore((s) => s._hydrated);

  useEffect(() => {
    // Wait until hydration is done before checking auth.
    // Without this, every page refresh kicks logged-in users to /login.
    if (!hydrated) return;

    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [hydrated, isAuthenticated, router]);

  // isReady = hydration done AND user is authenticated
  return { isReady: hydrated && isAuthenticated };
}
