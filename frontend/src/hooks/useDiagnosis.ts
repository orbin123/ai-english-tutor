"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { diagnosisApi } from "@/lib/diagnosis-api";
import type { DiagnosisInput } from "@/lib/validators/diagnosis";
import { useDiagnosisStore } from "@/store/diagnosisStore";

export function useDiagnosis() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const setResult = useDiagnosisStore((s) => s.setResult);

  return useMutation({
    mutationFn: (data: DiagnosisInput) => diagnosisApi.submit(data),
    onSuccess: (result) => {
      // Save result for the result page to display
      setResult(result);

      // Navigate to the result page FIRST — before invalidating /me.
      // If we invalidate first, the useEffect guard on diagnosis/page.tsx
      // sees diagnosis_completed=true and redirects to /dashboard,
      // skipping the result page entirely (race condition).
      router.push("/diagnosis/result");

      // Delay the /me refetch until after navigation has started.
      // The result page will call invalidateQueries itself when the
      // user clicks "Go to dashboard".
    },
  });
}
