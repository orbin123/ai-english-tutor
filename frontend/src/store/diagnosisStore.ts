import { create } from "zustand";
import type { DiagnosisResult } from "@/lib/diagnosis-api";

interface DiagnosisState {
  result: DiagnosisResult | null;
  setResult: (result: DiagnosisResult) => void;
  clear: () => void;
}

// Holds the diagnosis result for the result screen.
// Lives in memory only — refresh = lose it (which is fine; user can re-fetch
// via a future /diagnosis/result endpoint if we add one).
export const useDiagnosisStore = create<DiagnosisState>((set) => ({
  result: null,
  setResult: (result) => set({ result }),
  clear: () => set({ result: null }),
}));
