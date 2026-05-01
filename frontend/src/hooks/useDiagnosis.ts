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
      // Refetch /me so route guards see diagnosis_completed=true
      queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push("/diagnosis/result");
    },
  });
}
