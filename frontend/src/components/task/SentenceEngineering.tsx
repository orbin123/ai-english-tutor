"use client";

import { useEffect, useState } from "react";
import type { UseFormRegister, UseFormSetValue, FieldErrors } from "react-hook-form";
import type { SentenceEngineeringActivity } from "@/lib/tasks-api";

type FormValues = Record<string, string>;

interface Props {
  activity: SentenceEngineeringActivity;
  register: UseFormRegister<FormValues>;
  setValue: UseFormSetValue<FormValues>;
  errors: FieldErrors<FormValues>;
}

/**
 * Renders one Sentence-Engineering activity with chip UI.
 *
 * For each question we show the words as clickable chips. Click a chip
 * to add it to the sentence; click a placed word to send it back. The
 * resulting sentence is mirrored into react-hook-form via setValue so
 * the parent's submit handler sees it like any other field.
 */
export function SentenceEngineering({
  activity,
  register,
  setValue,
  errors,
}: Props) {
  const questionEntries = Object.entries(activity.questions);

  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-700">{activity.instruction}</p>

      {questionEntries.map(([qKey, q], i) => (
        <SentenceBuilder
          key={qKey}
          qKey={qKey}
          index={i + 1}
          words={q.words}
          register={register}
          setValue={setValue}
          errorMessage={errors[qKey]?.message as string | undefined}
        />
      ))}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// One question = one builder. Owns its own pick/unpick state.
// ───────────────────────────────────────────────────────────────────
interface BuilderProps {
  qKey: string;
  index: number;
  words: string[];
  register: UseFormRegister<FormValues>;
  setValue: UseFormSetValue<FormValues>;
  errorMessage?: string;
}

function SentenceBuilder({
  qKey,
  index,
  words,
  register,
  setValue,
  errorMessage,
}: BuilderProps) {
  // Track picks by ORIGINAL INDEX, not by word — handles duplicate words
  // (e.g. "I think I know" has two "I"s) without collapsing them.
  const [picked, setPicked] = useState<number[]>([]);

  const pickedSet = new Set(picked);
  const remainingIndexes = words
    .map((_, idx) => idx)
    .filter((idx) => !pickedSet.has(idx));

  const sentence = picked.map((idx) => words[idx]).join(" ");
  const allPicked = picked.length === words.length;

  // Mirror the assembled sentence into react-hook-form.
  // Validation runs every time it changes.
  useEffect(() => {
    setValue(qKey, sentence, { shouldValidate: true });
  }, [sentence, qKey, setValue]);

  // Register the field once, hidden — required by react-hook-form so it
  // tracks errors and includes the field in submit values.
  // We set rules here (required + all-words-used).
  const reg = register(qKey, {
    required: "Please build the sentence",
    validate: () =>
      allPicked || `Use all ${words.length} words to build the sentence`,
  });

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-gray-700">
        {index}. Tap the words in order to build the sentence:
      </p>

      {/* Assembly area — placed words */}
      <div
        className={
          "min-h-[44px] rounded border-2 border-dashed p-2 " +
          (allPicked
            ? "border-green-300 bg-green-50"
            : "border-gray-300 bg-gray-50")
        }
      >
        {picked.length === 0 ? (
          <span className="text-sm italic text-gray-400">
            Tap words below to start…
          </span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {picked.map((idx) => (
              <button
                key={`p-${idx}`}
                type="button"
                onClick={() =>
                  setPicked((prev) => prev.filter((i) => i !== idx))
                }
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
                title="Click to remove"
              >
                {words[idx]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Bank of remaining words */}
      <div className="flex flex-wrap gap-2">
        {remainingIndexes.length === 0 ? (
          <span className="text-xs italic text-gray-400">
            All words used. Tap a placed word to undo.
          </span>
        ) : (
          remainingIndexes.map((idx) => (
            <button
              key={`b-${idx}`}
              type="button"
              onClick={() => setPicked((prev) => [...prev, idx])}
              className="rounded border border-gray-300 bg-white px-3 py-1 text-sm text-gray-800 hover:bg-gray-100"
            >
              {words[idx]}
            </button>
          ))
        )}
      </div>

      {/* Hidden field — RHF needs it registered to validate */}
      <input type="hidden" {...reg} />

      {errorMessage && <p className="text-sm text-red-600">{errorMessage}</p>}
    </div>
  );
}
