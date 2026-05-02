"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/lib/auth-api";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { coursesApi } from "@/lib/courses-api";

export default function DashboardPage() {
  const router = useRouter();
  const { logout } = useAuthStore();
  const { isReady } = useRequireAuth();

  // Fetch user info using the token (proves token works)
  const { data: user, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isReady,
  });
  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: coursesApi.list,
    enabled: isReady && !!user?.diagnosis_completed && !user?.enrollment,
  });

  // If diagnosis not done, redirect to diagnosis flow
  useEffect(() => {
    if (user && !user.diagnosis_completed) router.replace("/diagnosis");
  }, [user, router]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!isReady) return null;

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <p className="text-gray-600">Loading your dashboard…</p>
      </main>
    );
  }

  const enrollment = user?.enrollment;

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-3xl space-y-6 rounded-lg border border-gray-200 p-8">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-gray-700">
          Welcome, <span className="font-medium">{user?.name}</span> 👋
        </p>
        <p className="text-sm text-gray-500">Email: {user?.email}</p>

        {enrollment ? (
          <section className="space-y-4 rounded-lg border border-blue-200 bg-blue-50 p-6">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-blue-700">
                Active course
              </p>
              <h2 className="text-xl font-semibold text-gray-900">
                {enrollment.course.title}
              </h2>
              <p className="text-sm text-gray-700">
                Week {enrollment.current_week}, Day{" "}
                {enrollment.current_day_in_week} of your plan
              </p>
            </div>

            <button
              onClick={() => router.push("/task")}
              className="w-full rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
            >
              Start today&apos;s task
            </button>
          </section>
        ) : (
          <section className="space-y-5 rounded-lg border border-amber-200 bg-amber-50 p-6">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-amber-700">
                Choose your learning plan
              </p>
              <h2 className="text-xl font-semibold text-gray-900">
                Purchase a course to unlock your daily tasks
              </h2>
              <p className="text-sm text-gray-700">
                Your diagnosis is complete. Pick a course to enroll instantly
                and start today&apos;s practice.
              </p>
            </div>

            {coursesQuery.isLoading ? (
              <p className="text-sm text-gray-600">Loading course options…</p>
            ) : coursesQuery.isError ? (
              <p className="text-sm text-red-700">
                We could not load course options right now, but you can still
                open the course page and try again there.
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {coursesQuery.data?.map((course) => (
                  <article
                    key={course.id}
                    className="rounded-lg border border-amber-200 bg-white p-4"
                  >
                    <div className="space-y-2">
                      <p className="text-sm font-medium text-amber-700">
                        {course.duration_weeks} weeks
                      </p>
                      <h3 className="text-lg font-semibold text-gray-900">
                        {course.title}
                      </h3>
                      <p className="text-sm leading-6 text-gray-600">
                        {course.description}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            )}

            <button
              onClick={() => router.push("/courses")}
              className="w-full rounded bg-amber-600 px-4 py-2 text-white hover:bg-amber-700"
            >
              View courses
            </button>
          </section>
        )}

        <button
          onClick={handleLogout}
          className="w-full rounded bg-gray-800 px-4 py-2 text-white hover:bg-gray-900"
        >
          Log out
        </button>
      </div>
    </main>
  );
}
