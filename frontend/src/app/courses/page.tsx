"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { useRouter } from "next/navigation";

import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/lib/auth-api";
import { coursesApi } from "@/lib/courses-api";
import { getApiErrorMessage } from "@/lib/errors";

export default function CoursesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isAuthenticated } = useAuthStore();
  const [pendingSlug, setPendingSlug] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isAuthenticated,
  });

  useEffect(() => {
    if (meQuery.data && !meQuery.data.diagnosis_completed) {
      router.replace("/diagnosis");
    }
  }, [meQuery.data, router]);

  useEffect(() => {
    if (meQuery.data?.enrollment) {
      router.replace("/dashboard");
    }
  }, [meQuery.data?.enrollment, router]);

  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: coursesApi.list,
    enabled:
      isAuthenticated &&
      !!meQuery.data?.diagnosis_completed &&
      !meQuery.data?.enrollment,
  });

  const purchaseMutation = useMutation({
    mutationFn: (courseSlug: string) =>
      coursesApi.enroll({ course_slug: courseSlug }),
    onMutate: (courseSlug) => {
      setPendingSlug(courseSlug);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["me"] }),
        queryClient.invalidateQueries({ queryKey: ["courses"] }),
      ]);
      router.push("/dashboard");
    },
    onError: async (error) => {
      const status = (error as AxiosError)?.response?.status;
      if (status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["me"] });
        router.push("/dashboard");
      }
    },
    onSettled: () => {
      setPendingSlug(null);
    },
  });

  if (!isAuthenticated) return null;

  if (meQuery.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-gray-600">Loading your account…</p>
      </main>
    );
  }

  if (meQuery.data && !meQuery.data.diagnosis_completed) return null;
  if (meQuery.data?.enrollment) return null;

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-4xl space-y-6 rounded-lg border border-gray-200 p-8">
        <div className="space-y-2">
          <p className="text-sm font-medium uppercase tracking-wide text-amber-700">
            Course purchase
          </p>
          <h1 className="text-3xl font-semibold text-gray-900">
            Choose the plan that unlocks your daily tasks
          </h1>
          <p className="text-sm leading-6 text-gray-600">
            Payments are skipped in this MVP. Purchasing a course enrolls you
            immediately so you can continue straight into practice.
          </p>
        </div>

        {coursesQuery.isLoading ? (
          <p className="text-gray-600">Loading course options…</p>
        ) : coursesQuery.isError ? (
          <div className="space-y-4 rounded-lg border border-red-200 bg-red-50 p-6">
            <h2 className="text-lg font-semibold text-red-800">
              We could not load the courses
            </h2>
            <p className="text-sm text-red-700">
              {getApiErrorMessage(coursesQuery.error)}
            </p>
            <button
              onClick={() => coursesQuery.refetch()}
              className="rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
            >
              Try again
            </button>
          </div>
        ) : !coursesQuery.data?.length ? (
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
            <p className="text-sm text-gray-700">
              No active courses are available yet.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {coursesQuery.data.map((course) => {
              const isPending =
                purchaseMutation.isPending && pendingSlug === course.slug;

              return (
                <article
                  key={course.id}
                  className="flex h-full flex-col justify-between rounded-lg border border-gray-200 bg-white p-6"
                >
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-amber-700">
                      {course.duration_weeks} weeks
                    </p>
                    <h2 className="text-2xl font-semibold text-gray-900">
                      {course.title}
                    </h2>
                    <p className="text-sm leading-6 text-gray-600">
                      {course.description}
                    </p>
                  </div>

                  <div className="mt-6 space-y-3">
                    <button
                      onClick={() => purchaseMutation.mutate(course.slug)}
                      disabled={purchaseMutation.isPending}
                      className="w-full rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {isPending ? "Purchasing…" : "Purchase"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {purchaseMutation.isError &&
          (purchaseMutation.error as AxiosError)?.response?.status !== 409 && (
            <p className="rounded bg-red-50 p-3 text-sm text-red-700">
              {getApiErrorMessage(purchaseMutation.error)}
            </p>
          )}

        <button
          onClick={() => router.push("/dashboard")}
          className="w-full rounded border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
        >
          Back to dashboard
        </button>
      </div>
    </main>
  );
}
