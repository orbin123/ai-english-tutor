"use client";

import type { UseFormRegister, FieldErrors } from "react-hook-form";
import type { ParaphrasingActivity } from "@/lib/tasks-api";

type FormValues = Record<string, string>;

interface Props {
  activity: ParaphrasingActivity;
  register: UseFormRegister<FormValues>;
  errors: FieldErrors<FormValues>;
}

/**
 * Renders one Paraphrasing activity.
 *
 * For each question we show the original sentence and a textarea where
 * the user types their rewrite. We also enforce `min_words` client-side
 * so the user gets immediate feedback before submitting (the backend
 * also enforces it as a safety net).
 */
export function Paraphrasing({ activity, register, errors }: Props) {
  const questionEntries = Object.entries(activity.questions);
  const minWords = activity.min_words ?? 4;

  return (
    <div className="space-y-5">
      <p className="text-sm text-gray-900">{activity.instruction}</p>

      {questionEntries.map(([qKey, original], i) => (
        <div key={qKey} className="space-y-2">
          <p className="text-sm font-medium text-gray-900">
            {i + 1}. Rewrite this sentence:
          </p>
          <blockquote className="rounded bg-blue-50 p-3 text-sm italic text-blue-900">
            “{original}”
          </blockquote>
          <textarea
            rows={2}
            autoComplete="off"
            {...register(qKey, {
              required: "Please write your paraphrase",
              setValueAs: (v: string) => v.trim(),
              validate: (v) =>
                v.split(/\s+/).filter(Boolean).length >= minWords ||
                `Use at least ${minWords} words`,
            })}
            className="w-full rounded border border-gray-300 bg-white px-3 py-2 text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none"
            placeholder="Your paraphrase…"
          />
          {errors[qKey] && (
            <p className="text-sm text-red-600">
              {errors[qKey]?.message as string}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
