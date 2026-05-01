"use client";

import { useEffect, useMemo } from "react";
import { useForm } from "react-hook-form";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";

import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/lib/auth-api";
import { useNextTask } from "@/hooks/useNextTask";
import { useSubmitResponse } from "@/hooks/useSubmitResponse";
import { getApiErrorMessage } from "@/lib/errors";
import {
  TaskRenderer,
  defaultValuesFor,
} from "@/components/task/TaskRenderer";

// Form shape: one string answer per question key (Q1, Q2, ...)
type FormValues = Record<string, string>;

export default function TaskPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  // ─── Route guards ──────────────────────────────────────────
  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  // Force diagnosis-first: if not done, send them there
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isAuthenticated,
  });
  const me = meQuery.data;
  useEffect(() => {
    if (me && !me.diagnosis_completed) router.replace("/diagnosis");
  }, [me, router]);

  // ─── Data ──────────────────────────────────────────────────
  const taskQuery = useNextTask(
    isAuthenticated && !!me?.diagnosis_completed && !!me?.enrollment,
  );
  const submit = useSubmitResponse();

  // We pick the FIRST activity in the task. (Today every seed has exactly
  // one scorable activity; when we bundle multiple per task, this becomes
  // a list + step indicator.)
  const activity = useMemo(
    () => taskQuery.data?.task.content.activities[0],
    [taskQuery.data],
  );

  // Default values keyed by Q1, Q2, ... — depends on which activity we got.
  const defaultValues: FormValues = useMemo(
    () => (activity ? defaultValuesFor(activity) : {}),
    [activity],
  );

  const {
    register,
    setValue,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues });

  // When the task arrives (or changes), reset the form with fresh keys.
  useEffect(() => {
    reset(defaultValues);
  }, [defaultValues, reset]);

  const onSubmit = (values: FormValues) => {
    if (!taskQuery.data) return;
    submit.mutate({
      user_task_id: taskQuery.data.id,
      content: values,
    });
  };

  // ─── Render states ─────────────────────────────────────────
  if (!isAuthenticated) return null;

  if (meQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-gray-600">Loading your account…</p>
      </main>
    );
  }

  if (me && !me.enrollment) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md space-y-4 rounded-lg border border-amber-200 bg-amber-50 p-6">
          <h2 className="text-lg font-semibold text-amber-900">
            Choose a course first
          </h2>
          <p className="text-sm text-amber-800">
            Your diagnosis is ready, but you need to purchase a course before
            we can unlock today&apos;s task.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex-1 rounded border border-amber-300 px-4 py-2 text-amber-900 hover:bg-amber-100"
            >
              Back to dashboard
            </button>
            <button
              onClick={() => router.push("/courses")}
              className="flex-1 rounded bg-amber-600 px-4 py-2 text-white hover:bg-amber-700"
            >
              View courses
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (taskQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-gray-600">Loading your task…</p>
      </main>
    );
  }

  if (taskQuery.isError) {
    const status = (taskQuery.error as AxiosError)?.response?.status;
    const message = getApiErrorMessage(taskQuery.error);
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md space-y-4 rounded-lg border border-red-200 bg-red-50 p-6">
          <h2 className="text-lg font-semibold text-red-800">
            We could not load a task
          </h2>
          <p className="text-sm text-red-700">{message}</p>
          {status === 404 && (
            <p className="text-sm text-red-700">
              You need an active course enrollment before we can assign a daily
              task.
            </p>
          )}
          <div className="flex gap-3">
            {status === 404 ? (
              <>
                <button
                  onClick={() => router.push("/dashboard")}
                  className="flex-1 rounded border border-red-300 px-4 py-2 text-red-800 hover:bg-red-100"
                >
                  Back to dashboard
                </button>
                <button
                  onClick={() => router.push("/courses")}
                  className="flex-1 rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
                >
                  View courses
                </button>
              </>
            ) : (
              <button
                onClick={() => taskQuery.refetch()}
                className="rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
              >
                Try again
              </button>
            )}
          </div>
        </div>
      </main>
    );
  }

  if (!taskQuery.data || !activity) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-gray-600">
          Today&apos;s task has no activity. Please try again later.
        </p>
      </main>
    );
  }

  const { task } = taskQuery.data;
  const passage = task.content.source.text;

  return (
    <main className="flex min-h-screen items-start justify-center px-4 py-10">
      <div className="w-full max-w-2xl space-y-6 rounded-lg border border-gray-200 p-8">
        {/* Header */}
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Today&apos;s task · {task.task_type}
          </p>
          <h1 className="mt-1 text-2xl font-semibold">{task.title}</h1>
        </div>

        {/* Instruction + passage */}
        <section className="space-y-3">
          <p className="text-sm text-gray-700">{task.content.instruction}</p>
          <blockquote className="rounded bg-gray-50 p-4 italic leading-relaxed text-gray-800">
            {passage}
          </blockquote>
        </section>

        {/* Activity + submit */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <TaskRenderer
            activity={activity}
            register={register}
            setValue={setValue}
            errors={errors}
          />

          {submit.error && (
            <p className="rounded bg-red-50 p-2 text-sm text-red-700">
              {getApiErrorMessage(submit.error)}
            </p>
          )}

          <div className="flex justify-between">
            <button
              type="button"
              onClick={() => router.push("/dashboard")}
              className="rounded border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
            >
              Back to dashboard
            </button>
            <button
              type="submit"
              disabled={submit.isPending}
              className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submit.isPending ? "Submitting…" : "Submit answer"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
