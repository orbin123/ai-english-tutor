"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTaskStore } from "@/store/taskStore";

// Pretty labels for skill keys (same set used on diagnosis result)
const SKILL_LABELS: Record<string, string> = {
  grammar: "Grammar",
  vocabulary: "Vocabulary",
  pronunciation: "Pronunciation",
  fluency: "Fluency",
  expression: "Expression",
  tone: "Tone",
  comprehension: "Comprehension",
};

// The Feedback Agent returns a `body` JSON. Shape can vary, so we render
// it defensively. We try a few common keys; otherwise we show JSON.
type FeedbackBody = {
  summary?: string;
  praise?: string;
  corrections?: Array<{
    question?: string;
    your_answer?: string;
    correct_answer?: string;
    why?: string;
    rule?: string;
  }>;
  practice_tip?: string;
  [key: string]: unknown;
};

export default function TaskResultPage() {
  const router = useRouter();
  const { result, clear } = useTaskStore();

  // No result in memory (e.g. page refresh) → send back to /task
  useEffect(() => {
    if (!result) router.replace("/task");
  }, [result, router]);

  if (!result) return null;

  const { evaluation, feedback, skill_scores } = result;
  const fb = feedback.body as FeedbackBody;

  const goNext = () => {
    clear();
    router.push("/task"); // will fetch the next task (cache was invalidated)
  };

  const goDashboard = () => {
    clear();
    router.push("/dashboard");
  };

  return (
    <main className="flex min-h-screen items-start justify-center px-4 py-10">
      <div className="w-full max-w-2xl space-y-6 rounded-lg border border-gray-200 p-8">
        {/* Header — overall score */}
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold">Your result</h1>
          <p className="text-3xl font-bold text-blue-600">
            {evaluation.percentage.toFixed(0)}%
          </p>
        </div>
        <p className="text-sm text-gray-600">
          Overall score: {evaluation.overall_score.toFixed(2)}
        </p>

        {/* Feedback summary / praise */}
        {(fb.summary || fb.praise) && (
          <section className="space-y-2 rounded bg-blue-50 p-4">
            {fb.summary && (
              <p className="text-sm text-blue-900">{fb.summary}</p>
            )}
            {fb.praise && (
              <p className="text-sm italic text-blue-800">{fb.praise}</p>
            )}
          </section>
        )}

        {/* Corrections */}
        {Array.isArray(fb.corrections) && fb.corrections.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
              What to fix
            </h2>
            <ul className="space-y-3">
              {fb.corrections.map((c, i) => (
                <li
                  key={i}
                  className="rounded border border-amber-200 bg-amber-50 p-3 text-sm"
                >
                  {c.question && (
                    <p className="text-gray-800">
                      <span className="font-medium">Question:</span>{" "}
                      {c.question}
                    </p>
                  )}
                  {c.your_answer !== undefined && (
                    <p className="text-red-700">
                      <span className="font-medium">Your answer:</span>{" "}
                      {c.your_answer || <em>(blank)</em>}
                    </p>
                  )}
                  {c.correct_answer && (
                    <p className="text-green-700">
                      <span className="font-medium">Correct answer:</span>{" "}
                      {c.correct_answer}
                    </p>
                  )}
                  {c.why && (
                    <p className="mt-1 text-gray-700">
                      <span className="font-medium">Why:</span> {c.why}
                    </p>
                  )}
                  {c.rule && (
                    <p className="text-gray-600">
                      <span className="font-medium">Rule:</span> {c.rule}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Practice tip */}
        {fb.practice_tip && (
          <section className="rounded bg-gray-50 p-3 text-sm text-gray-800">
            <span className="font-medium">Tip:</span> {fb.practice_tip}
          </section>
        )}

        {/* Skill scores */}
        {skill_scores.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-medium uppercase tracking-wide text-gray-500">
              Updated skill scores
            </h2>
            <ul className="space-y-2">
              {skill_scores.map((s) => {
                const pct = Math.min((s.score / 4) * 100, 100);
                return (
                  <li key={s.skill_id}>
                    <div className="flex justify-between text-sm">
                      <span>{SKILL_LABELS[s.skill_name] ?? s.skill_name}</span>
                      <span className="text-gray-600">
                        {s.score.toFixed(2)}
                      </span>
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
          </section>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={goDashboard}
            className="flex-1 rounded border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
          >
            Back to dashboard
          </button>
          <button
            onClick={goNext}
            className="flex-1 rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            Next task
          </button>
        </div>
      </div>
    </main>
  );
}
