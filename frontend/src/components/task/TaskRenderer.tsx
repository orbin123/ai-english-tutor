"use client";

import type { UseFormRegister, UseFormSetValue, FieldErrors } from "react-hook-form";
import type { TaskActivity } from "@/lib/tasks-api";

import { FillInBlanks } from "./FillInBlanks";
import { Paraphrasing } from "./Paraphrasing";
import { SentenceEngineering } from "./SentenceEngineering";

type FormValues = Record<string, string>;

interface Props {
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
export function TaskRenderer({ activity, register, setValue, errors }: Props) {
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
