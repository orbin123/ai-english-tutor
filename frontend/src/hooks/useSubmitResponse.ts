"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { tasksApi } from "@/lib/tasks-api";
import { useTaskStore } from "@/store/taskStore";

/**
 * Submits the user's answers and runs the full grading loop on the backend
 * (response → evaluation → feedback → skill score update).
 *
 * On success:
 *  - Saves the graded bundle to the task store
 *  - Invalidates the cached task so the next visit fetches a fresh one
 *  - Navigates to /task/result
 */
export function useSubmitResponse() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const setResult = useTaskStore((s) => s.setResult);

  return useMutation({
    mutationFn: (payload: {
      user_task_id: number;
      content: Record<string, string>;
      raw_text?: string;
    }) => tasksApi.submitResponse(payload),
    onSuccess: (graded) => {
      setResult(graded);
      // Current task is now completed; clear so /task fetches the next one.
      queryClient.invalidateQueries({ queryKey: ["task", "next"] });
      router.push("/task/result");
    },
  });
}
