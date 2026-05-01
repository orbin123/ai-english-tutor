"use client";

import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import {
  diagnosisSchema,
  type DiagnosisFormInput,
  type DiagnosisInput,
} from "@/lib/validators/diagnosis";
import { useDiagnosis } from "@/hooks/useDiagnosis";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/lib/auth-api";
import { getApiErrorMessage } from "@/lib/errors";

// ────────────────────────────────────────────────────────────────────
// Static content for the diagnosis tasks
// ────────────────────────────────────────────────────────────────────

// Fill-blank questions — answers must match backend's FILL_BLANK_ANSWERS_V1
const FILL_BLANK_QUESTIONS = [
  'She ____ to school every morning.       (hint: "go" in correct form)',
  'I ____ rice for lunch yesterday.        (hint: "eat" in past tense)',
  'It always ____ a lot in July.           (hint: "rain" in correct form)',
  'They ____ in Mumbai for ten years.      (hint: "live" in past tense)',
  'The novel ____ by a famous author.      (hint: "write" in passive past)',
];

const READ_ALOUD_PASSAGE = `Every morning I wake up early and walk in the park. The fresh air helps me think clearly. I greet a few neighbours, finish a short jog, and return home feeling ready for the day.`;

// 4 step labels for the stepper
const STEPS = ["About you", "Fill the blanks", "Short writing", "Read aloud"];

// Step-1 default values (so the radios/select aren't undefined)
const DEFAULT_VALUES: DiagnosisFormInput = {
  self_assessment: {
    self_assessed_level: "beginner",
    goal: "professional",
    daily_time_minutes: 15,
    content_exposure: "low",
    interests: [],
  },
  fill_blank: { answers: ["", "", "", "", ""] },
  writing: { response_text: "" },
  read_aloud: { acknowledged: false as unknown as true }, // satisfies literal(true) at runtime
};

// ────────────────────────────────────────────────────────────────────

export default function DiagnosisPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [step, setStep] = useState(0);

  // Route guard: must be logged in
  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  // If already done, send to dashboard
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isAuthenticated,
  });
  useEffect(() => {
    if (me?.diagnosis_completed) router.replace("/dashboard");
  }, [me, router]);

  const {
    register,
    handleSubmit,
    trigger,
    control,
    formState: { errors },
  } = useForm<DiagnosisFormInput, unknown, DiagnosisInput>({
    resolver: zodResolver(diagnosisSchema),
    defaultValues: DEFAULT_VALUES,
    mode: "onTouched",
  });

  const diagnosis = useDiagnosis();

  // Validate only the current step's fields before moving on
  const goNext = async () => {
    const fieldGroups = [
      ["self_assessment"],
      ["fill_blank"],
      ["writing"],
      ["read_aloud"],
    ] as const;
    const ok = await trigger(fieldGroups[step]);
    if (ok) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const onSubmit = (data: DiagnosisInput) => diagnosis.mutate(data);

  if (!isAuthenticated) return null;

  return (
    <main className="flex min-h-screen items-start justify-center px-4 py-10">
      <div className="w-full max-w-2xl space-y-6 rounded-lg border border-gray-200 p-8">
        <h1 className="text-2xl font-semibold">English Diagnosis</h1>

        {/* Stepper */}
        <ol className="flex gap-2 text-sm">
          {STEPS.map((label, i) => (
            <li
              key={label}
              className={`flex-1 rounded px-2 py-1 text-center ${
                i === step
                  ? "bg-blue-600 text-white"
                  : i < step
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {i + 1}. {label}
            </li>
          ))}
        </ol>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
          {/* ─── Step 1: Self assessment ──────────────────────────── */}
          {step === 0 && (
            <section className="space-y-4">
              <p className="text-gray-600">
                Tell us a little about yourself. This helps us pick the right
                starting point.
              </p>

              <div>
                <label className="block text-sm font-medium">
                  How would you rate your English?
                </label>
                <select
                  {...register("self_assessment.self_assessed_level")}
                  className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
                >
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium">
                  What is your main goal?
                </label>
                <select
                  {...register("self_assessment.goal")}
                  className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
                >
                  <option value="casual">Casual learning</option>
                  <option value="professional">Professional / Job</option>
                  <option value="academic">Academic / Studies</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium">
                  How many minutes can you study per day?
                </label>
                <input
                  type="number"
                  min={5}
                  max={240}
                  {...register("self_assessment.daily_time_minutes")}
                  className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
                />
                {errors.self_assessment?.daily_time_minutes && (
                  <p className="mt-1 text-sm text-red-600">
                    {errors.self_assessment.daily_time_minutes.message}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium">
                  How often do you read or listen to English content?
                </label>
                <select
                  {...register("self_assessment.content_exposure")}
                  className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
                >
                  <option value="none">Never</option>
                  <option value="low">Sometimes</option>
                  <option value="medium">Often</option>
                  <option value="high">Daily</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium">
                  Pick up to 3 interests (optional)
                </label>
                <Controller
                  name="self_assessment.interests"
                  control={control}
                  render={({ field }) => (
                    <div className="mt-1 flex flex-wrap gap-2">
                      {[
                        "tech",
                        "business",
                        "movies",
                        "sports",
                        "travel",
                        "music",
                      ].map((tag) => {
                        const checked = field.value.includes(tag);
                        return (
                          <label
                            key={tag}
                            className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${
                              checked
                                ? "border-blue-600 bg-blue-50 text-blue-700"
                                : "border-gray-300 text-gray-700"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="hidden"
                              checked={checked}
                              onChange={() => {
                                if (checked) {
                                  field.onChange(
                                    field.value.filter((t) => t !== tag),
                                  );
                                } else if (field.value.length < 3) {
                                  field.onChange([...field.value, tag]);
                                }
                              }}
                            />
                            {tag}
                          </label>
                        );
                      })}
                    </div>
                  )}
                />
              </div>
            </section>
          )}

          {/* ─── Step 2: Fill blanks ──────────────────────────── */}
          {step === 1 && (
            <section className="space-y-4">
              <p className="text-gray-600">
                Fill each blank with one or two words.
              </p>
              {FILL_BLANK_QUESTIONS.map((q, i) => (
                <div key={i}>
                  <label className="block text-sm">
                    {i + 1}. {q}
                  </label>
                  <input
                    type="text"
                    {...register(`fill_blank.answers.${i}` as const)}
                    className="mt-1 w-full rounded border border-gray-300 px-3 py-2"
                  />
                  {errors.fill_blank?.answers?.[i] && (
                    <p className="mt-1 text-sm text-red-600">
                      {errors.fill_blank.answers[i]?.message}
                    </p>
                  )}
                </div>
              ))}
            </section>
          )}

          {/* ─── Step 3: Writing ──────────────────────────── */}
          {step === 2 && (
            <section className="space-y-4">
              <p className="text-gray-600">
                <strong>Prompt:</strong> Describe your typical day in 3–5
                sentences.
              </p>
              <textarea
                rows={6}
                {...register("writing.response_text")}
                className="w-full rounded border border-gray-300 px-3 py-2"
                placeholder="I usually wake up at..."
              />
              {errors.writing?.response_text && (
                <p className="text-sm text-red-600">
                  {errors.writing.response_text.message}
                </p>
              )}
            </section>
          )}

          {/* ─── Step 4: Read aloud (stub) ──────────────────────────── */}
          {step === 3 && (
            <section className="space-y-4">
              <p className="text-gray-600">
                Read this passage aloud naturally. (Audio recording is coming
                soon — for now, just check the box once you have read it.)
              </p>
              <blockquote className="rounded bg-gray-50 p-4 italic text-gray-800">
                {READ_ALOUD_PASSAGE}
              </blockquote>
              <label className="flex items-start gap-2 text-sm">
                <Controller
                  name="read_aloud.acknowledged"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="checkbox"
                      checked={!!field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="mt-1"
                    />
                  )}
                />
                I have read the passage aloud.
              </label>
              {errors.read_aloud?.acknowledged && (
                <p className="text-sm text-red-600">
                  {errors.read_aloud.acknowledged.message}
                </p>
              )}

              {diagnosis.error && (
                <p className="rounded bg-red-50 p-2 text-sm text-red-700">
                  {getApiErrorMessage(diagnosis.error)}
                </p>
              )}
            </section>
          )}

          {/* ─── Nav buttons ──────────────────────────── */}
          <div className="flex justify-between">
            <button
              type="button"
              onClick={goBack}
              disabled={step === 0}
              className="rounded border border-gray-300 px-4 py-2 disabled:opacity-50"
            >
              Back
            </button>
            {step < STEPS.length - 1 ? (
              <button
                type="button"
                onClick={goNext}
                className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
              >
                Next
              </button>
            ) : (
              <button
                type="submit"
                disabled={diagnosis.isPending}
                className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {diagnosis.isPending ? "Submitting..." : "Submit diagnosis"}
              </button>
            )}
          </div>
        </form>
      </div>
    </main>
  );
}
