"use client";

import type { UseFormRegister, UseFormSetValue, FieldErrors } from "react-hook-form";
import type {
  TaskActivity,
  GeneratedTaskContent,
  GeneratedTaskType,
  FillInBlanksTaskContent,
  ErrorSpottingTaskContent,
  SentenceTransformationTaskContent,
  VoiceConversionTaskContent,
  ErrorCorrectionTaskContent,
} from "@/lib/tasks-api";

// ── Old activity-based components (seeded tasks) ──
import { FillInBlanks } from "./FillInBlanks";
import { Paraphrasing } from "./Paraphrasing";
import { SentenceEngineering } from "./SentenceEngineering";

// ── New generated-task components ──
import { GeneratedFillInBlanks } from "./GeneratedFillInBlanks";
import { GeneratedErrorSpotting } from "./GeneratedErrorSpotting";
import { GeneratedSentenceTransformation } from "./GeneratedSentenceTransformation";
import { GeneratedVoiceConversion } from "./GeneratedVoiceConversion";
import { GeneratedErrorCorrection } from "./GeneratedErrorCorrection";

type FormValues = Record<string, string>;

// ════════════════════════════════════════════════════════════════════
// GENERATED TASK RENDERER — dispatches on taskType (from task.task_type)
// ════════════════════════════════════════════════════════════════════

interface GeneratedTaskRendererProps {
  /** task.task_type from the outer UserTask — NOT from inside content */
  taskType: GeneratedTaskType;
  content: GeneratedTaskContent;
  onSubmit: (answers: Record<string, string>) => void;
  isPending: boolean;
}

/**
 * Picks the right generated-task component based on `taskType`.
 *
 * The `taskType` comes from `task.task_type` on the outer UserTask object,
 * NOT from inside `content` — the backend's Pydantic models (GeneratedTaskBase)
 * don't serialize a `task_type` field inside the content JSON.
 */
export function GeneratedTaskRenderer({
  taskType,
  content,
  onSubmit,
  isPending,
}: GeneratedTaskRendererProps) {
  switch (taskType) {
    case "fill_in_blanks":
      return (
        <GeneratedFillInBlanks
          content={content as FillInBlanksTaskContent}
          onSubmit={onSubmit}
          isPending={isPending}
        />
      );
    case "error_spotting":
      return (
        <GeneratedErrorSpotting
          content={content as ErrorSpottingTaskContent}
          onSubmit={onSubmit}
          isPending={isPending}
        />
      );
    case "sentence_transformation":
      return (
        <GeneratedSentenceTransformation
          content={content as SentenceTransformationTaskContent}
          onSubmit={onSubmit}
          isPending={isPending}
        />
      );
    case "voice_conversion":
      return (
        <GeneratedVoiceConversion
          content={content as VoiceConversionTaskContent}
          onSubmit={onSubmit}
          isPending={isPending}
        />
      );
    case "error_correction":
      return (
        <GeneratedErrorCorrection
          content={content as ErrorCorrectionTaskContent}
          onSubmit={onSubmit}
          isPending={isPending}
        />
      );
    default:
      return (
        <p style={{ fontSize: 14, color: "oklch(45% 0.07 240)" }}>
          This task type ({taskType}) is not supported yet.
        </p>
      );
  }
}

// ════════════════════════════════════════════════════════════════════
// SEEDED (OLD) ACTIVITY RENDERER — dispatches on activity_type
// Kept for backward compatibility with hand-seeded tasks.
// ════════════════════════════════════════════════════════════════════

interface SeededActivityProps {
  activity: TaskActivity;
  register: UseFormRegister<FormValues>;
  setValue: UseFormSetValue<FormValues>;
  errors: FieldErrors<FormValues>;
}

/**
 * Picks the right activity renderer based on `activity_type`.
 *
 * Adding a new activity later means: add a new component, import it,
 * add one branch here. The page does not change.
 *
 * The discriminated union on `activity.activity_type` lets TypeScript
 * narrow the activity to the right shape inside each branch, so each
 * sub-component gets a strongly-typed prop.
 */
export function TaskRenderer({ activity, register, setValue, errors }: SeededActivityProps) {
  switch (activity.activity_type) {
    case "fill_in_the_blanks":
      return (
        <FillInBlanks activity={activity} register={register} errors={errors} />
      );
    case "paraphrasing":
      return (
        <Paraphrasing activity={activity} register={register} errors={errors} />
      );
    case "sentence_engineering":
      return (
        <SentenceEngineering
          activity={activity}
          register={register}
          setValue={setValue}
          errors={errors}
        />
      );
    default: {
      // Exhaustiveness check — if a new activity_type is added to the
      // union but not handled here, TypeScript will fail to compile.
      const _exhaustive: never = activity;
      void _exhaustive;
      return (
        <p className="text-sm text-gray-600">
          This activity type is not supported yet.
        </p>
      );
    }
  }
}

/**
 * Helper: build the default form values object given an activity.
 * Each question key starts as an empty string.
 *
 * Kept here (next to TaskRenderer) so all per-activity-shape knowledge
 * stays in one folder.
 */
export function defaultValuesFor(activity: TaskActivity): FormValues {
  return Object.keys(activity.questions).reduce<FormValues>((acc, k) => {
    acc[k] = "";
    return acc;
  }, {});
}
