import { create } from "zustand";
import type { ResponseGraded } from "@/lib/tasks-api";

interface TaskState {
  result: ResponseGraded | null;
  setResult: (result: ResponseGraded) => void;
  clear: () => void;
}

// Holds the latest graded task result for the result screen.
// In-memory only — same approach as diagnosisStore.
// On refresh the user is sent back to /task to start fresh.
export const useTaskStore = create<TaskState>((set) => ({
  result: null,
  setResult: (result) => set({ result }),
  clear: () => set({ result: null }),
}));
