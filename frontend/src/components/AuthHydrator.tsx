"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/store/authStore";

/**
 * Runs once on app load. Reads token from localStorage into Zustand store.
 * Without this, the store starts empty on every page refresh.
 */
export function AuthHydrator() {
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return null;  // renders nothing — pure side-effect component
}