"use client";

import type { UseFormRegister, FieldErrors } from "react-hook-form";
import type { FillInBlanksActivity } from "@/lib/tasks-api";

type FormValues = Record<string, string>;

interface Props {
  activity: FillInBlanksActivity;
  register: UseFormRegister<FormValues>;
  errors: FieldErrors<FormValues>;
}

/**
 * Renders one Fill-in-the-Blanks activity.
 *
 * The parent <TaskRenderer /> owns the react-hook-form `useForm()` instance
 * so all three activity components stay dumb — they just declare which
 * fields they need.
 */
export function FillInBlanks({ activity, register, errors }: Props) {
  const questionEntries = Object.entries(activity.questions);

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-700">{activity.instruction}</p>

      {questionEntries.map(([qKey, qText], i) => (
        <div key={qKey}>
          <label className="block text-sm">
            <span className="font-medium text-gray-700">
              {i + 1}. {qText}
            </span>
          </label>
          <input
            type="text"
            autoComplete="off"
            {...register(qKey, {
              required: "Please type an answer",
              setValueAs: (v: string) => v.trim(),
            })}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
            placeholder="Your answer"
          />
          {errors[qKey] && (
            <p className="mt-1 text-sm text-red-600">
              {errors[qKey]?.message as string}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
