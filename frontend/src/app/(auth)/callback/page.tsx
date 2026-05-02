"use client";

/**
 * /auth/callback
 *
 * After Google OAuth the backend redirects here with:
 *   ?token=<jwt>&next=dashboard|diagnosis
 *
 * This page:
 *  1. Reads the token from the URL
 *  2. Saves it to the auth store (and localStorage)
 *  3. Redirects to the right page
 */

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

export default function AuthCallbackPage() {
  const router = useRouter();
  const params = useSearchParams();
  const setToken = useAuthStore((s) => s.setToken);

  useEffect(() => {
    const token = params.get("token");
    const next = params.get("next") ?? "dashboard";

    if (!token) {
      // Something went wrong — send back to login
      router.replace("/login?error=google_failed");
      return;
    }

    // Save JWT exactly the same way normal login does
    setToken(token);

    // Go to the right page
    router.replace(`/${next}`);
  }, [params, router, setToken]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-slate-500">Signing you in…</p>
    </div>
  );
}
