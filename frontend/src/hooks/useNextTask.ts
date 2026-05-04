"use client";

import { useQuery } from "@tanstack/react-query";
import { tasksApi } from "@/lib/tasks-api";

/**
 * Fetches the user's day bundle (array of tasks).
 *
 * Backend `/tasks/next` is idempotent: calling it repeatedly the same day
 * returns the same bundle. So it's safe to refetch / retry on focus.
 *
 * `enabled` lets the caller pause the fetch until the user is authenticated.
 */
export function useNextTask(enabled = true) {
  return useQuery({
    queryKey: ["task", "next"],
    queryFn: tasksApi.getNext,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 min — same bundle; no need to spam the server
    retry: false, // don't retry on 404/409/503 — those are real states
  });
}
