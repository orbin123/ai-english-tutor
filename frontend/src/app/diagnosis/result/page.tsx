"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useDiagnosisStore } from "@/store/diagnosisStore";

// Pretty labels for skill keys
const SKILL_LABELS: Record<string, string> = {
  grammar: "Grammar",
  vocabulary: "Vocabulary",
  pronunciation: "Pronunciation",
  fluency: "Fluency",
  expression: "Expression",
  tone: "Tone",
  comprehension: "Comprehension",
};

export default function DiagnosisResultPage() {
  const router = useRouter();
  const { result, clear } = useDiagnosisStore();

  // If user lands here without a result (e.g. refresh), send back
  useEffect(() => {
    if (!result) router.replace("/diagnosis");
  }, [result, router]);

  if (!result) return null;

  const continueToDashboard = () => {
    clear();
    router.push("/dashboard");
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-xl space-y-6 rounded-lg border border-gray-200 p-8">
        <div>
          <h1 className="text-2xl font-semibold">Your starting profile</h1>
          <p className="mt-1 text-gray-600">{result.next_step}</p>
        </div>

        {/* Skill scores */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
            Skill scores (out of 4)
          </h2>
          <ul className="space-y-2">
            {Object.entries(result.skill_scores).map(([key, score]) => {
              const pct = Math.min((score / 4) * 100, 100);
              return (
                <li key={key}>
                  <div className="flex justify-between text-sm">
                    <span>{SKILL_LABELS[key] ?? key}</span>
                    <span className="text-gray-600">{score.toFixed(2)}</span>
                  </div>
                  <div className="mt-1 h-2 w-full rounded bg-gray-100">
                    <div
                      className="h-2 rounded bg-blue-600"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Weakest skills */}
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
            We will focus on
          </h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {result.weakest_skills.map((s) => (
              <span
                key={s}
                className="rounded-full bg-amber-50 px-3 py-1 text-sm text-amber-800"
              >
                {SKILL_LABELS[s] ?? s}
              </span>
            ))}
          </div>
        </div>

        <button
          onClick={continueToDashboard}
          className="w-full rounded bg-blue-600 py-2 text-white hover:bg-blue-700"
        >
          Go to dashboard
        </button>
      </div>
    </main>
  );
}
