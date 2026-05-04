"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useForm } from "react-hook-form";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";

import { useAuthStore } from "@/store/authStore";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { authApi } from "@/lib/auth-api";
import { useNextTask } from "@/hooks/useNextTask";
import { getApiErrorMessage } from "@/lib/errors";
import { tasksApi, isGeneratedTaskType } from "@/lib/tasks-api";
import type { UserTask, ResponseGraded, GeneratedTaskContent, SeededTaskContent } from "@/lib/tasks-api";
import {
  TaskRenderer,
  GeneratedTaskRenderer,
  defaultValuesFor,
} from "@/components/task/TaskRenderer";

// Form shape: one string answer per question key (Q1, Q2, ...)
type FormValues = Record<string, string>;

// ════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ════════════════════════════════════════════════════════════════════

export default function TaskPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { isReady, isSuperUser } = useRequireAuth();

  // ─── Superuser jump override ───────────────────────────────
  // When the dev panel calls superuser-jump, it stashes the returned
  // bundle in sessionStorage so we can render it immediately without
  // an extra /tasks/next call.
  const [overrideBundle, setOverrideBundle] = useState<UserTask[] | null>(null);
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem("superuser_jump_bundle");
      if (raw) {
        sessionStorage.removeItem("superuser_jump_bundle");
        setOverrideBundle(JSON.parse(raw) as UserTask[]);
      }
    } catch { /* ignore parse errors */ }
  }, []);

  // Force diagnosis-first: if not done, send them there
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isReady,
  });
  const me = meQuery.data;
  useEffect(() => {
    if (me && !me.diagnosis_completed && !isSuperUser) router.replace("/diagnosis");
  }, [me, isSuperUser, router]);

  // ─── Data ──────────────────────────────────────────────────
  // Skip the normal fetch when we already have a jump override
  const taskQuery = useNextTask(
    !overrideBundle && isReady && !!me?.diagnosis_completed && !!me?.enrollment,
  );

  const bundle: UserTask[] = overrideBundle ?? taskQuery.data ?? [];
  const totalTasks = bundle.length;

  // ─── Step state ────────────────────────────────────────────
  const [currentStep, setCurrentStep] = useState(0);
  const [results, setResults] = useState<(ResponseGraded | null)[]>([]);
  const [dayComplete, setDayComplete] = useState(false);

  // Reset step when bundle changes
  useEffect(() => {
    if (bundle.length > 0) {
      setCurrentStep(0);
      setResults(new Array(bundle.length).fill(null));
      setDayComplete(false);
    }
  }, [bundle.length]);

  const currentTask = bundle[currentStep] ?? null;
  const isLastTask = currentStep === totalTasks - 1;

  // ─── Detect task kind ────────────────────────────────────────
  const taskType = currentTask?.task.task_type ?? "";
  const isGenerated = isGeneratedTaskType(taskType);

  // ─── Seeded task form (only used for old tasks) ────────────
  const activity = useMemo(() => {
    if (!currentTask || isGenerated) return null;
    const c = currentTask.task.content as SeededTaskContent;
    return c.activities?.[0] ?? null;
  }, [currentTask, isGenerated]);

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

  useEffect(() => {
    reset(defaultValues);
  }, [defaultValues, reset]);

  // ─── Submit mutation ───────────────────────────────────────
  const submitMutation = useMutation({
    mutationFn: (payload: {
      user_task_id: number;
      content: Record<string, string>;
    }) => tasksApi.submitResponse(payload),
    onSuccess: (graded) => {
      setResults((prev) => {
        const next = [...prev];
        next[currentStep] = graded;
        return next;
      });

      if (isLastTask) {
        setDayComplete(true);
      } else {
        setCurrentStep((s) => s + 1);
      }
    },
  });

  // ─── Handlers ──────────────────────────────────────────────

  // Seeded task submit (through react-hook-form)
  const onSeededSubmit = (values: FormValues) => {
    if (!currentTask) return;
    submitMutation.mutate({
      user_task_id: currentTask.id,
      content: values,
    });
  };

  // Generated task submit (from the component's own onSubmit)
  const onGeneratedSubmit = useCallback(
    (answers: Record<string, string>) => {
      if (!currentTask) return;
      submitMutation.mutate({
        user_task_id: currentTask.id,
        content: answers,
      });
    },
    [currentTask, submitMutation],
  );

  // Complete day
  const completeDayMutation = useMutation({
    mutationFn: tasksApi.completeDay,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task", "next"] });
      queryClient.invalidateQueries({ queryKey: ["me"] });
      router.push("/dashboard");
    },
  });

  // ─── Render states ─────────────────────────────────────────
  if (!isReady) return null;

  if (meQuery.isLoading) {
    return (
      <PageShell>
        <LoadingState message="Loading your account…" />
      </PageShell>
    );
  }

  if (me && !me.enrollment) {
    return (
      <PageShell>
        <NoEnrollmentCard onDashboard={() => router.push("/dashboard")} onCourses={() => router.push("/courses")} />
      </PageShell>
    );
  }

  if (taskQuery.isLoading) {
    return (
      <PageShell>
        <LoadingState message="Loading today's tasks…" />
      </PageShell>
    );
  }

  if (taskQuery.isError) {
    const status = (taskQuery.error as AxiosError)?.response?.status;
    const message = getApiErrorMessage(taskQuery.error);
    return (
      <PageShell>
        <ErrorCard
          status={status}
          message={message}
          onRetry={() => taskQuery.refetch()}
          onDashboard={() => router.push("/dashboard")}
          onCourses={() => router.push("/courses")}
        />
      </PageShell>
    );
  }

  if (totalTasks === 0) {
    return (
      <PageShell>
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <p style={{ fontSize: 15, color: "oklch(45% 0.07 240)" }}>
            No tasks available for today. Check back later!
          </p>
          <button
            onClick={() => router.push("/dashboard")}
            style={{
              marginTop: 16,
              padding: "10px 24px",
              borderRadius: 10,
              border: "1px solid rgba(80,120,200,0.15)",
              background: "rgba(255,255,255,0.85)",
              color: "oklch(30% 0.08 240)",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Back to dashboard
          </button>
        </div>
      </PageShell>
    );
  }

  // ─── Day complete screen ───────────────────────────────────
  if (dayComplete) {
    const enrollment = me?.enrollment;
    const dayNum = enrollment
      ? (enrollment.current_week - 1) * 7 + enrollment.current_day_in_week
      : 0;

    return (
      <PageShell>
        <DayCompleteScreen
          dayNum={dayNum}
          results={results}
          bundle={bundle}
          isCompleting={completeDayMutation.isPending}
          onFinish={() => completeDayMutation.mutate()}
        />
      </PageShell>
    );
  }

  // ─── Active task view ──────────────────────────────────────
  const content = currentTask.task.content;
  const isSeeded = !isGenerated;

  return (
    <PageShell>
      {/* Progress indicator */}
      <ProgressBar current={currentStep} total={totalTasks} />

      {/* Task header */}
      <div style={{ marginBottom: 20 }}>
        <p
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "oklch(52% 0.18 240)",
            margin: "0 0 6px",
          }}
        >
          Task {currentStep + 1} of {totalTasks} · {currentTask.task.task_type.replace(/_/g, " ")}
        </p>
        <h1
          style={{
            fontSize: 22,
            fontWeight: 800,
            color: "oklch(15% 0.09 245)",
            margin: 0,
            letterSpacing: "-0.02em",
          }}
        >
          {currentTask.task.title}
        </h1>
      </div>

      {/* Generated task — self-contained, no form wrapper needed */}
      {isGenerated && (
        <GeneratedTaskRenderer
          taskType={taskType as import("@/lib/tasks-api").GeneratedTaskType}
          content={content as GeneratedTaskContent}
          onSubmit={onGeneratedSubmit}
          isPending={submitMutation.isPending}
        />
      )}

      {/* Seeded task — uses react-hook-form */}
      {isSeeded && activity && (
        <>
          <section style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
            <p style={{ fontSize: 14, color: "oklch(40% 0.07 240)", lineHeight: 1.6, margin: 0 }}>
              {(content as SeededTaskContent).instruction}
            </p>
            <blockquote
              style={{
                margin: 0,
                padding: "14px 18px",
                borderRadius: 10,
                background: "oklch(96% 0.015 240)",
                borderLeft: "3px solid oklch(52% 0.18 240)",
                fontSize: 14,
                fontStyle: "italic",
                color: "oklch(25% 0.07 240)",
                lineHeight: 1.7,
              }}
            >
              {(content as SeededTaskContent).source.text}
            </blockquote>
          </section>

          <form onSubmit={handleSubmit(onSeededSubmit)} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <TaskRenderer
              activity={activity}
              register={register}
              setValue={setValue}
              errors={errors}
            />

            {submitMutation.error && (
              <p
                style={{
                  padding: "8px 12px",
                  borderRadius: 8,
                  background: "oklch(95% 0.04 15)",
                  fontSize: 13,
                  color: "oklch(40% 0.15 15)",
                }}
              >
                {getApiErrorMessage(submitMutation.error)}
              </p>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                style={{
                  padding: "10px 20px",
                  borderRadius: 10,
                  border: "1px solid rgba(80,120,200,0.15)",
                  background: "rgba(255,255,255,0.85)",
                  color: "oklch(30% 0.08 240)",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                Back to dashboard
              </button>
              <button
                type="submit"
                disabled={submitMutation.isPending}
                style={{
                  padding: "10px 24px",
                  borderRadius: 10,
                  border: "none",
                  background: "oklch(52% 0.18 240)",
                  color: "white",
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  opacity: submitMutation.isPending ? 0.6 : 1,
                }}
              >
                {submitMutation.isPending
                  ? "Submitting…"
                  : isLastTask
                    ? "Submit & Finish Day"
                    : "Submit & Next →"}
              </button>
            </div>
          </form>
        </>
      )}

      {/* Error from generated task submit */}
      {isGenerated && submitMutation.error && (
        <p
          style={{
            marginTop: 12,
            padding: "8px 12px",
            borderRadius: 8,
            background: "oklch(95% 0.04 15)",
            fontSize: 13,
            color: "oklch(40% 0.15 15)",
          }}
        >
          {getApiErrorMessage(submitMutation.error)}
        </p>
      )}
    </PageShell>
  );
}

// ════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ════════════════════════════════════════════════════════════════════

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        fontFamily: "'Plus Jakarta Sans', sans-serif",
        background:
          "radial-gradient(ellipse 80% 60% at 50% 0%, oklch(86% 0.07 240) 0%, oklch(90% 0.045 245) 50%, oklch(93% 0.025 250) 100%)",
        position: "relative",
      }}
    >
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap"
      />

      {/* Dotted pattern overlay */}
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          backgroundImage:
            "radial-gradient(circle, rgba(90,130,210,0.18) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
          zIndex: 0,
        }}
      />

      <div
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: 680,
          margin: "0 auto",
          padding: "40px 20px 80px",
        }}
      >
        {/* Glass card container */}
        <div
          style={{
            background: "rgba(255,255,255,0.85)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            borderRadius: 18,
            border: "1px solid rgba(255,255,255,0.9)",
            padding: "28px 28px 24px",
            boxShadow:
              "0 4px 32px rgba(80,110,180,0.1), 0 1.5px 6px rgba(80,120,200,0.05)",
            animation: "fadeSlideUp 0.4s ease both",
          }}
        >
          {children}
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse-soft {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.7; }
        }
      `}</style>
    </div>
  );
}

// ─── Progress bar ────────────────────────────────────────────

function ProgressBar({ current, total }: { current: number; total: number }) {
  return (
    <div style={{ marginBottom: 24 }}>
      {/* Dots */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          marginBottom: 10,
        }}
      >
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            style={{
              width: i === current ? 32 : 10,
              height: 10,
              borderRadius: 5,
              background:
                i < current
                  ? "oklch(55% 0.18 155)" // completed — green
                  : i === current
                    ? "oklch(52% 0.18 240)" // active — blue
                    : "oklch(88% 0.03 240)", // upcoming — light
              transition: "all 0.3s ease",
            }}
          />
        ))}
      </div>

      {/* Bar */}
      <div
        style={{
          height: 4,
          borderRadius: 2,
          background: "oklch(92% 0.02 240)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${((current) / total) * 100}%`,
            borderRadius: 2,
            background:
              "linear-gradient(90deg, oklch(55% 0.18 155), oklch(52% 0.18 240))",
            transition: "width 0.4s ease",
          }}
        />
      </div>
    </div>
  );
}

// ─── Day complete screen ─────────────────────────────────────

function DayCompleteScreen({
  dayNum,
  results,
  bundle,
  isCompleting,
  onFinish,
}: {
  dayNum: number;
  results: (ResponseGraded | null)[];
  bundle: UserTask[];
  isCompleting: boolean;
  onFinish: () => void;
}) {
  return (
    <div
      style={{
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 24,
      }}
    >
      {/* Celebration icon */}
      <div
        style={{
          width: 72,
          height: 72,
          borderRadius: "50%",
          background:
            "linear-gradient(135deg, oklch(55% 0.18 155), oklch(52% 0.18 240))",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          animation: "fadeSlideUp 0.5s ease both",
        }}
      >
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
          <path
            d="M9 12l2 2 4-4"
            stroke="white"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle
            cx="12"
            cy="12"
            r="9"
            stroke="white"
            strokeWidth="2"
            fill="none"
          />
        </svg>
      </div>

      <div>
        <h2
          style={{
            fontSize: 24,
            fontWeight: 800,
            color: "oklch(15% 0.09 245)",
            margin: "0 0 6px",
            letterSpacing: "-0.02em",
          }}
        >
          Day {dayNum} complete!
        </h2>
        <p
          style={{
            fontSize: 15,
            color: "oklch(45% 0.07 240)",
            margin: 0,
          }}
        >
          Great work! See you tomorrow for your next session.
        </p>
      </div>

      {/* Score badges */}
      <div
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
        {bundle.map((task, i) => {
          const result = results[i];
          const score = result?.evaluation?.percentage;
          return (
            <div
              key={task.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 18px",
                borderRadius: 12,
                background: "oklch(96% 0.015 240)",
                border: "1px solid rgba(80,120,200,0.1)",
                animation: `fadeSlideUp 0.4s ease ${0.1 + i * 0.1}s both`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                }}
              >
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    background:
                      score != null && score >= 70
                        ? "oklch(55% 0.18 155)"
                        : score != null && score >= 50
                          ? "oklch(60% 0.18 70)"
                          : "oklch(55% 0.15 15)",
                    color: "white",
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {i + 1}
                </span>
                <div>
                  <p
                    style={{
                      fontSize: 14,
                      fontWeight: 600,
                      color: "oklch(20% 0.07 240)",
                      margin: 0,
                    }}
                  >
                    {task.task.title}
                  </p>
                  <p
                    style={{
                      fontSize: 12,
                      color: "oklch(50% 0.06 240)",
                      margin: 0,
                    }}
                  >
                    {task.task.task_type.replace(/_/g, " ")}
                  </p>
                </div>
              </div>
              {score != null && (
                <span
                  style={{
                    fontSize: 16,
                    fontWeight: 800,
                    color:
                      score >= 70
                        ? "oklch(45% 0.18 155)"
                        : score >= 50
                          ? "oklch(50% 0.18 70)"
                          : "oklch(50% 0.18 15)",
                  }}
                >
                  {Math.round(score)}%
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Finish button */}
      <button
        onClick={onFinish}
        disabled={isCompleting}
        style={{
          width: "100%",
          padding: "14px 0",
          borderRadius: 12,
          border: "none",
          background: "oklch(52% 0.18 240)",
          color: "white",
          fontSize: 15,
          fontWeight: 700,
          cursor: isCompleting ? "not-allowed" : "pointer",
          transition: "all 0.2s ease",
          opacity: isCompleting ? 0.6 : 1,
          marginTop: 4,
        }}
      >
        {isCompleting ? "Completing…" : "Back to dashboard →"}
      </button>
    </div>
  );
}

// ─── Loading state ───────────────────────────────────────────

function LoadingState({ message }: { message: string }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "48px 0",
      }}
    >
      {/* Spinner */}
      <div
        style={{
          width: 36,
          height: 36,
          border: "3px solid oklch(88% 0.03 240)",
          borderTopColor: "oklch(52% 0.18 240)",
          borderRadius: "50%",
          margin: "0 auto 16px",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <p style={{ fontSize: 14, color: "oklch(45% 0.07 240)" }}>
        {message}
      </p>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

// ─── No enrollment card ──────────────────────────────────────

function NoEnrollmentCard({
  onDashboard,
  onCourses,
}: {
  onDashboard: () => void;
  onCourses: () => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <span
        style={{
          display: "inline-block",
          fontSize: 12,
          fontWeight: 700,
          color: "oklch(45% 0.16 70)",
          background: "oklch(92% 0.06 80)",
          padding: "3px 10px",
          borderRadius: 20,
          width: "fit-content",
        }}
      >
        Action required
      </span>
      <h2
        style={{
          fontSize: 20,
          fontWeight: 800,
          color: "oklch(15% 0.09 245)",
          margin: 0,
          letterSpacing: "-0.02em",
        }}
      >
        Choose a course first
      </h2>
      <p
        style={{
          fontSize: 14,
          color: "oklch(45% 0.07 240)",
          margin: 0,
          lineHeight: 1.5,
        }}
      >
        Your diagnosis is ready, but you need to purchase a course before we
        can unlock today&apos;s tasks.
      </p>
      <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
        <button
          onClick={onDashboard}
          style={{
            flex: 1,
            padding: "10px 0",
            borderRadius: 10,
            border: "1px solid rgba(80,120,200,0.15)",
            background: "rgba(255,255,255,0.8)",
            color: "oklch(30% 0.08 240)",
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Back to dashboard
        </button>
        <button
          onClick={onCourses}
          style={{
            flex: 1,
            padding: "10px 0",
            borderRadius: 10,
            border: "none",
            background: "oklch(52% 0.18 240)",
            color: "white",
            fontSize: 14,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          View courses
        </button>
      </div>
    </div>
  );
}

// ─── Error card ──────────────────────────────────────────────

function ErrorCard({
  status,
  message,
  onRetry,
  onDashboard,
  onCourses,
}: {
  status?: number;
  message: string;
  onRetry: () => void;
  onDashboard: () => void;
  onCourses: () => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <h2
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: "oklch(40% 0.18 15)",
          margin: 0,
        }}
      >
        We could not load your tasks
      </h2>
      <p style={{ fontSize: 14, color: "oklch(45% 0.12 15)", margin: 0 }}>
        {message}
      </p>
      {status === 404 && (
        <p style={{ fontSize: 14, color: "oklch(45% 0.12 15)", margin: 0 }}>
          You need an active course enrollment before we can assign daily
          tasks.
        </p>
      )}
      <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
        {status === 404 ? (
          <>
            <button
              onClick={onDashboard}
              style={{
                flex: 1,
                padding: "10px 0",
                borderRadius: 10,
                border: "1px solid oklch(85% 0.04 15)",
                background: "rgba(255,255,255,0.8)",
                color: "oklch(40% 0.12 15)",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Back to dashboard
            </button>
            <button
              onClick={onCourses}
              style={{
                flex: 1,
                padding: "10px 0",
                borderRadius: 10,
                border: "none",
                background: "oklch(55% 0.18 15)",
                color: "white",
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              View courses
            </button>
          </>
        ) : (
          <button
            onClick={onRetry}
            style={{
              padding: "10px 24px",
              borderRadius: 10,
              border: "none",
              background: "oklch(55% 0.18 15)",
              color: "white",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
