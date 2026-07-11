"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  LayoutDashboard,
  MessageCircle,
  MoreHorizontal,
  RotateCcw,
  Sparkles,
} from "lucide-react";

import { api, refreshAccessToken } from "@/lib/api";
import { WS_BASE_URL } from "@/lib/api-config";
import { useAuthStore } from "@/store/authStore";
import {
  buildLearningWsUrl,
  HEARTBEAT_INTERVAL_MS,
  nextReconnectDelayMs,
  reconnectExhausted,
  shouldScheduleReconnect,
} from "@/lib/ws-reconnect";
import { ReconnectNotice } from "@/components/chat/ReconnectNotice";
import { authApi } from "@/lib/auth-api";

import { tasksApi } from "@/lib/tasks-api";
import {
  extensionForMime,
  isVoiceRecordingSupported,
  useVoiceRecorder,
} from "@/lib/hooks/useVoiceRecorder";
import { markDailyChatEntered, markScorecardViewed } from "@/lib/daily-session-entry";
import {
  CoachSkeleton,
  TaskChatLoadingSkeleton,
  type TaskChatLoadingType,
} from "@/components/chat/TaskChatSkeletons";
import { AppConfirmDialog } from "@/components/ui/AppConfirmDialog";
import { SessionScorecard as DaySessionScorecard } from "@/components/sessions/SessionScorecard";
import {
  learningSessionApi,
  type CompletedActivitySummary,
  type LearningSessionState,
  type SessionScorecardRead,
  type PronunciationResult,
} from "@/lib/sessions-api";
import {
  WIDGET_COMPONENTS,
  WIDGET_SECTION_LABEL,
  normalizeWidgetKey,
} from "@/components/chat/runtimeMapping";
import type {
  AnyTaskPayload,
  WidgetKey,
} from "@/components/chat/runtimeMapping";
import {
  RuntimeEvaluationCard,
  RuntimeFeedbackCard,
  RuntimeFinalScorecard,
  RuntimeRagFeedback,
} from "@/components/chat/runtimeReviewMapping";
import { adaptContractTask, rawContractTaskWidget } from "@/components/chat/contractTaskAdapter";
import { TaskWidgetRenderer } from "@/components/chat/tasks/task_widgets/TaskWidgetRenderer";
import {
  ChatBubble,
  ChatGlobalStyles,
  ChatMain,
  ChatPageShell,
  ChatTopbar,
  LessonMetaCard,
  SectionMarker,
} from "@/components/chat/ChatChrome";
import { ChatFormattedText } from "@/components/chat/ChatFormattedText";

/* ── Score / Feedback payloads (rendered by chat session, not by widgets) ── */
interface ScorecardPayload {
  overall_score: number;
  skill_name: string;
  topic: string;
  total?: number;
  correct_count?: number;
  answered_count?: number;
  questions?: Record<string, unknown>;
  rubric_scores?: Record<string, number>;
  weighted_points?: Record<string, number>;
  subskill_score?: number | null;
}

interface RuntimeBlueprintPayload {
  blueprint?: {
    teaching?: {
      lesson_goal?: string;
      lesson_description?: string;
      focus?: string;
      topic?: string;
      skill_name?: string;
    };
    activities?: RuntimeActivityContract[];
    final_review?: Record<string, unknown>;
  };
  _session?: RuntimeSessionMeta;
}

type RuntimeBlueprint = NonNullable<RuntimeBlueprintPayload["blueprint"]>;

interface RuntimeSessionMeta {
  theme_type?: string | null;
  cefr_level?: string | null;
  day_number?: number | string | null;
  week_number?: number | string | null;
}

interface LessonMeta {
  title: string;
  focus: string;
  theme: string;
  cefr: string;
  dayNumber: number | null;
}

type RuntimeActivityContract = Record<string, unknown> & {
  activity_id?: string;
  sequence?: number;
  archetype_id?: string;
  activity?: string;
  task_widget?: string;
  evaluation_widget?: string;
  feedback_widget?: string;
};

interface FinalScorecardPayload {
  points_earned?: Record<string, number>;
  skill_labels?: Record<string, string>;
  activities?: Array<{
    sequence?: number;
    archetype_id?: string;
    raw_score?: number;
    base_reward?: number;
  }>;
  mentor_note?: string | null;
}

interface RagFeedbackPayload {
  mentor_note?: string | null;
  available?: boolean;
  pending?: boolean;
  scorecard_id?: number | null;
}

interface FeedbackError {
  question_id: string;
  user_answer: string;
  correct_answer: string;
  correction?: string | null;
  error_type: string;
  why_wrong: string;
  rule: string;
  memory_tip: string;
}

interface FeedbackPayload {
  overall_message?: string;
  widget?: string;
  errors?: FeedbackError[];
  summary?: string;
  did_well?: string[];
  mistakes?: Array<{
    issue: string;
    user_wrote?: string | null;
    correction?: string | null;
    rule?: string | null;
    sub_skills_affected?: string[];
  }>;
  score: number;
  overall_level?: string;
  practice_suggestion?: string;
  next_tip?: string | null;
  sub_skill_breakdown?: Record<string, number>;
  // Backend ActivityFeedback row id + the viewer's reaction — drive the 👍/👎
  // reaction bar under the feedback card.
  feedback_id?: number | null;
  user_reaction?: "LIKE" | "DISLIKE" | null;
  // Pass-mark gating: present only when the learner has the gate enabled.
  gate?: { passed: boolean; score_pct: number; threshold_pct: number };
}

/* ── Pronunciation result payload ─────────────────────────────────────── */
interface PronunciationResultPayload {
  pronunciation: PronunciationResult;
  raw_score: number;
  reference_text: string;
  feedback: {
    score: number;
    summary?: string;
    did_well?: string[];
    mistakes?: Array<{ issue: string; rule?: string | null }>;
    next_tip?: string | null;
  };
}

/* ── Event log ───────────────────────────────────────────────────────── */
type ChatEvent =
  | { kind: "chat"; role: "ai" | "you"; content: string; actions?: string[]; streamId?: string; streaming?: boolean; retryTaskGen?: boolean; format?: "markdown" | "plain" }
  | { kind: "section"; tone: "intro" | "task" | "score" | "feedback"; label: string }
  | { kind: "task"; payload: AnyTaskPayload; submitted: boolean; answers: Record<string, unknown> }
  | { kind: "scorecard"; payload: ScorecardPayload }
  | { kind: "final_scorecard"; payload: FinalScorecardPayload }
  | { kind: "rag_feedback"; payload: RagFeedbackPayload }
  | { kind: "feedback"; payload: FeedbackPayload }
  | { kind: "pronunciation"; payload: PronunciationResultPayload };

type WSIncoming =
  | { type: "chat_message"; role?: string; content?: string; actions?: string[] }
  | { type: "chat_stream_start"; role?: string; stream_id?: string; actions?: string[] }
  | { type: "chat_stream_delta"; role?: string; stream_id?: string; content?: string }
  | { type: "chat_stream_end"; role?: string; stream_id?: string; content?: string; actions?: string[] }
  | { type: "ui_event"; widget: string; payload: Record<string, unknown> }
  | { type: "pong" }
  | { type: "error"; content?: string; code?: string };

type WSOutgoing =
  | { type: "user_message"; content: string }
  | { type: "task_submission"; answers: Record<string, unknown> }
  | { type: "follow_up_action"; action: string };

function isKnownWidget(widget: string): widget is WidgetKey {
  return normalizeWidgetKey(widget) in WIDGET_COMPONENTS;
}

function findRuntimeActivityContract(
  blueprint: RuntimeBlueprint | null,
  payload: Record<string, unknown>,
): RuntimeActivityContract | null {
  const activities = blueprint?.activities ?? [];
  if (!activities.length) return null;

  const activityId = String(payload.activity_id || "");
  const archetypeId = String(payload.archetype_id || "");
  const sequence = Number(payload.sequence || payload.activity_sequence || 0);

  return (
    activities.find((activity) => activityId && activity.activity_id === activityId) ||
    activities.find((activity) => archetypeId && activity.archetype_id === archetypeId) ||
    activities.find((activity) => sequence > 0 && Number(activity.sequence || 0) === sequence) ||
    null
  );
}

function shouldShowActivitySkeletonAfterChat(content?: string) {
  const text = (content || "").toLowerCase();
  return (
    text.includes("here is activity") ||
    text.includes("here is your practice task") ||
    text.includes("continue with activity")
  );
}

function sequenceFromMeta(payload: Record<string, unknown> | undefined): number | null {
  const meta = payload?._session as
    | { sequence?: number; current_task_index?: number }
    | undefined;
  if (meta && typeof meta.sequence === "number") return meta.sequence;
  if (meta && typeof meta.current_task_index === "number") return meta.current_task_index + 1;
  const direct = payload?.sequence;
  return typeof direct === "number" ? direct : null;
}

function activitySequence(activity: RuntimeActivityContract): number {
  return Number(activity.sequence ?? 0);
}

/**
 * Deterministic label for the task skeleton that holds the *next* activity's
 * slot. Reads the blueprint's ordered activities and the just-completed
 * sequence so the skeleton's section marker matches the label the real task
 * event will render (`WIDGET_SECTION_LABEL`), falling back to a broad
 * skill-bucket label from the archetype id.
 */
function nextActivitySkeletonLabel(
  blueprint: RuntimeBlueprint | null,
  currentSequence: number | null,
): string {
  const activities = blueprint?.activities ?? [];
  if (!activities.length) return "Practice task";
  const sorted = [...activities].sort((a, b) => activitySequence(a) - activitySequence(b));
  const next =
    currentSequence === null
      ? sorted[0]
      : (sorted.find((a) => activitySequence(a) > currentSequence) ?? sorted[sorted.length - 1]);
  if (!next) return "Practice task";

  const rawWidget = String(next.task_widget ?? "");
  if (rawWidget) return WIDGET_SECTION_LABEL[normalizeWidgetKey(rawWidget)];

  const raw = String(next.archetype_id ?? next.activity ?? "").toUpperCase();
  if (raw.includes("LISTEN")) return "Listening task";
  if (raw.includes("SPEAK")) return "Speaking task";
  if (raw.includes("WRIT")) return "Writing task";
  if (raw.includes("READ")) return "Reading task";
  return "Practice task";
}

/** True when `sequence` is the highest-sequence activity in the blueprint. */
function isLastActivitySequence(
  blueprint: RuntimeBlueprint | null,
  sequence: number | null,
): boolean {
  const activities = blueprint?.activities ?? [];
  if (!activities.length || sequence === null) return false;
  const maxSeq = Math.max(...activities.map(activitySequence));
  return sequence >= maxSeq;
}

const RETRY_ACTIVITY_ACTION = "Retry activity";
// Sent when the learner taps the retry icon on a failed-task-generation error
// bubble. The backend forces a fresh generation (bypassing the broken cached
// task) and re-delivers. Must match REGENERATE_TASK_ACTION in the backend.
const REGENERATE_TASK_ACTION = "Regenerate task";

function isNavigationPromptActions(actions?: string[]): boolean {
  return (
    actions?.some((label) => label === "Next activity" || label === "Go to dashboard") ?? false
  );
}

function retrySequenceFromEvents(events: ChatEvent[]): number | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const evt = events[i];
    if (evt.kind !== "scorecard" && evt.kind !== "pronunciation") continue;
    const seq = sequenceFromMeta(evt.payload as unknown as Record<string, unknown>);
    if (seq !== null) return seq;
  }
  return null;
}

function latestCompletedSummarySequence(
  summaries: CompletedActivitySummary[],
): number | null {
  if (!summaries.length) return null;
  return summaries[summaries.length - 1]?.sequence ?? null;
}

function navigationPromptActions(actions?: string[]): string[] | undefined {
  // "Retry activity" is kept as a first-class button (the pass-mark gate sends
  // it explicitly on a failed activity). The subtle icon-only retry affordance
  // is reserved for the normal "Next activity" prompt and is suppressed when
  // this explicit button is present (see `hasExplicitRetry` in the renderer).
  return actions;
}

function isDailyCompleteFarewell(content: string): boolean {
  return content.includes("Today's activities are complete");
}

/* ── Pass-mark gate "not passed" banner ───────────────────────────────── */
function PassMarkBanner({
  scorePct,
  thresholdPct,
}: {
  scorePct: number;
  thresholdPct: number;
}) {
  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        marginBottom: 10,
        padding: "11px 14px",
        borderRadius: 10,
        border: "1px solid oklch(82% 0.12 55)",
        background: "oklch(96% 0.045 70)",
        color: "oklch(40% 0.12 50)",
        fontSize: 13.5,
        fontWeight: 700,
      }}
    >
      <RotateCcw size={15} aria-hidden />
      <span>
        Not passed — you scored {scorePct}%, need {thresholdPct}% to advance.
        Retry this activity to move on.
      </span>
    </div>
  );
}

function hydrateResultEventsFromState(state: LearningSessionState): ChatEvent[] {
  if (!state.last_evaluation || !state.last_feedback) return [];
  const evaluation = state.last_evaluation as Record<string, unknown>;
  const feedback = state.last_feedback as Record<string, unknown>;
  const completed = state.completed_sequences ?? [];
  const sequence =
    (completed.length > 0 ? completed[completed.length - 1] : null) ??
    state.current_sequence;
  const sessionMeta =
    typeof sequence === "number" ? { sequence, current_task_index: sequence - 1 } : undefined;
  const scorecardPayload = {
    overall_score: Number(evaluation.raw_score ?? feedback.score ?? 0),
    skill_name: state.skill_name,
    topic: state.topic,
    rubric_scores: evaluation.rubric_scores as Record<string, number> | undefined,
    weighted_points: evaluation.weighted_points as Record<string, number> | undefined,
    _session: sessionMeta,
    sequence,
  } as ScorecardPayload & { _session?: { sequence: number; current_task_index: number }; sequence?: number };
  const feedbackPayload = {
    ...feedback,
    score: Number(feedback.score ?? evaluation.raw_score ?? 0),
  } as FeedbackPayload;
  return [
    { kind: "section", tone: "score", label: "Activity score" },
    { kind: "scorecard", payload: scorecardPayload },
    { kind: "section", tone: "feedback", label: "Activity feedback" },
    { kind: "feedback", payload: feedbackPayload },
  ];
}

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function displayLabel(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function buildLessonEyebrow(meta: LessonMeta): string {
  const parts = [
    meta.theme || "Lesson",
    meta.cefr,
    meta.dayNumber ? `Day ${meta.dayNumber}` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function SendIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
      <path d="M14 8L2.5 3L5 8L2.5 13L14 8Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" fill="currentColor" />
    </svg>
  );
}
function MicIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="6" y="2" width="4" height="7" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 13v1.5M5.5 14.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
/* ── Sub-components ──────────────────────────────────────────────────── */
function Topbar({
  onRestart,
  restarting,
  onRestartActivity,
  canRestartActivity,
  restartingActivity,
}: {
  onRestart: () => void;
  restarting: boolean;
  onRestartActivity: () => void;
  canRestartActivity: boolean;
  restartingActivity: boolean;
}) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [restartSubmenuOpen, setRestartSubmenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) setRestartSubmenuOpen(false);
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (restartSubmenuOpen) {
          setRestartSubmenuOpen(false);
        } else {
          setMenuOpen(false);
        }
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen, restartSubmenuOpen]);

  const goToDashboard = () => {
    setMenuOpen(false);
    router.push("/dashboard");
  };

  const restart = () => {
    setMenuOpen(false);
    onRestart();
  };

  const restartActivity = () => {
    setMenuOpen(false);
    onRestartActivity();
  };

  const restartBusy = restarting || restartingActivity;

  const menuItemStyle = (disabled: boolean): React.CSSProperties => ({
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 11px",
    borderRadius: 10,
    color: "oklch(28% 0.08 245)",
    fontSize: 13,
    fontWeight: 700,
    fontFamily: "inherit",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.55 : 1,
    textAlign: "left",
  });

  const submenuItemStyle = (disabled: boolean): React.CSSProperties => ({
    ...menuItemStyle(disabled),
    fontWeight: 600,
    fontSize: 12.5,
    whiteSpace: "nowrap",
  });

  const flyoutStyle: React.CSSProperties = {
    position: "absolute",
    left: "calc(100% + 6px)",
    top: 0,
    minWidth: 210,
    padding: 6,
    borderRadius: 14,
    background: "white",
    border: "1px solid oklch(85% 0.025 240)",
    boxShadow: "0 14px 34px rgba(35,55,100,0.18)",
    zIndex: 1,
  };

  return (
    <ChatTopbar
      subtitle="Chat session"
      onBack={() => router.push("/dashboard")}
      actions={
        <div ref={menuRef} style={{ position: "relative", overflow: "visible" }}>
          <style>{`
            .session-menu-option {
              border: none;
              background: transparent;
              transition: background 0.12s ease;
            }
            .session-menu-option:not(:disabled):hover {
              background: oklch(93% 0.03 240);
            }
            .session-menu-restart-row:not([data-busy="true"]) {
              transition: background 0.12s ease;
            }
            .session-menu-restart-row:not([data-busy="true"]):hover {
              background: oklch(93% 0.03 240);
            }
            .session-menu-restart-row[data-open="true"]:not([data-busy="true"]) {
              background: oklch(96% 0.02 240);
            }
            .session-menu-restart-row[data-open="true"]:not([data-busy="true"]):hover {
              background: oklch(91% 0.035 240);
            }
          `}</style>
          <button
            type="button"
            className="chat-round-icon-btn"
            aria-label="Session options"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
            style={{
              cursor: "pointer",
            }}
          >
            <MoreHorizontal size={17} strokeWidth={2.4} />
          </button>

          {menuOpen && (
            <div
              role="menu"
              aria-label="Session options"
              style={{
                position: "absolute",
                top: 44,
                right: 0,
                width: 210,
                padding: 6,
                borderRadius: 14,
                background: "white",
                border: "1px solid oklch(85% 0.025 240)",
                boxShadow: "0 14px 34px rgba(35,55,100,0.18)",
                overflow: "visible",
              }}
            >
              <div style={{ position: "relative", overflow: "visible" }}>
                <div
                  className="session-menu-restart-row"
                  data-busy={restartBusy ? "true" : "false"}
                  data-open={restartSubmenuOpen ? "true" : "false"}
                  style={{
                    display: "flex",
                    alignItems: "stretch",
                    borderRadius: 10,
                  }}
                >
                  <div
                    role="menuitem"
                    aria-disabled={restartBusy}
                    style={{
                      ...menuItemStyle(restartBusy),
                      flex: 1,
                      cursor: restartBusy ? "not-allowed" : "default",
                    }}
                  >
                    <RotateCcw size={15} />
                    {restartBusy ? "Restarting..." : "Restart"}
                  </div>
                  {!restartBusy && (
                    <button
                      type="button"
                      className="session-menu-option"
                      aria-label="Restart options"
                      aria-haspopup="menu"
                      aria-expanded={restartSubmenuOpen}
                      onClick={() => setRestartSubmenuOpen((open) => !open)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 32,
                        flexShrink: 0,
                        borderRadius: "0 10px 10px 0",
                        color: "oklch(28% 0.08 245)",
                        cursor: "pointer",
                      }}
                    >
                      <ChevronRight size={15} aria-hidden />
                    </button>
                  )}
                </div>
                {restartSubmenuOpen && !restartBusy && (
                  <div role="menu" aria-label="Restart options" style={flyoutStyle}>
                    {canRestartActivity && (
                      <button
                        type="button"
                        role="menuitem"
                        className="session-menu-option"
                        disabled={restartingActivity}
                        onClick={restartActivity}
                        style={submenuItemStyle(restartingActivity)}
                      >
                        Restart current activity
                      </button>
                    )}
                    <button
                      type="button"
                      role="menuitem"
                      className="session-menu-option"
                      disabled={restarting}
                      onClick={restart}
                      style={submenuItemStyle(restarting)}
                    >
                      Restart whole session
                    </button>
                  </div>
                )}
              </div>
              <button
                type="button"
                role="menuitem"
                className="session-menu-option"
                onClick={goToDashboard}
                style={menuItemStyle(false)}
              >
                <LayoutDashboard size={15} />
                Back to dashboard
              </button>
            </div>
          )}
        </div>
      }
    />
  );
}

function ChatPronunciationCard({ payload }: { payload: PronunciationResultPayload }) {
  const { pronunciation: p, raw_score, feedback } = payload;

  function scoreColor(score: number) {
    if (score >= 80) return "oklch(48% 0.18 155)";
    if (score >= 60) return "oklch(60% 0.13 80)";
    return "oklch(50% 0.15 25)";
  }
  function scoreBg(score: number) {
    if (score >= 80) return "oklch(96% 0.02 155)";
    if (score >= 60) return "oklch(98% 0.01 80)";
    return "oklch(98% 0.01 25)";
  }

  const pct = raw_score <= 10 ? Math.round(raw_score * 10) : Math.round(raw_score);
  const overallBg =
    pct >= 80 ? "oklch(48% 0.18 155)" :
    pct >= 60 ? "oklch(52% 0.18 240)" :
    pct >= 40 ? "oklch(60% 0.13 80)" :
               "oklch(58% 0.2 15)";

  const scores = [
    { label: "Accuracy", score: p.accuracy_score, desc: "Phoneme precision" },
    { label: "Fluency", score: p.fluency_score, desc: "Pacing \u0026 pauses" },
    { label: "Completeness", score: p.completeness_score, desc: "Words spoken" },
    ...(p.prosody_score != null && p.prosody_score > 0
      ? [{ label: "Prosody", score: p.prosody_score, desc: "Stress \u0026 rhythm" }]
      : []),
  ];

  return (
    <div
      style={{
        borderRadius: 22,
        background: "rgba(255,255,255,0.92)",
        backdropFilter: "blur(18px)",
        WebkitBackdropFilter: "blur(18px)",
        border: "1.5px solid rgba(255,255,255,0.92)",
        boxShadow: "0 8px 32px rgba(80,110,180,0.13)",
        overflow: "hidden",
        animation: "chatFadeIn 0.35s ease both",
        marginBottom: 16,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "20px 22px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid oklch(92% 0.01 245)",
        }}
      >
        <div>
          <div style={{ fontSize: 17, fontWeight: 800, color: "oklch(20% 0.09 245)", letterSpacing: "-0.01em" }}>
            Pronunciation Assessment
          </div>
          <div style={{ fontSize: 13, color: "oklch(45% 0.07 240)", marginTop: 3 }}>
            {feedback.summary || "Here is your detailed pronunciation feedback."}
          </div>
        </div>
        <div
          style={{
            background: overallBg,
            color: "white",
            borderRadius: 10,
            padding: "10px 16px",
            fontWeight: 800,
            fontSize: 20,
            minWidth: 72,
            textAlign: "center",
            boxShadow: "0 4px 14px rgba(0,0,0,0.08)",
            lineHeight: 1,
          }}
        >
          {pct}<span style={{ fontSize: 13, opacity: 0.85 }}>%</span>
        </div>
      </div>

      {/* Score breakdown bars */}
      <div style={{ padding: "16px 22px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
        {scores.map((s) => (
          <div
            key={s.label}
            style={{
              background: scoreBg(s.score),
              border: "1px solid oklch(93% 0.01 245)",
              padding: "12px 14px",
              borderRadius: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "oklch(20% 0.09 245)" }}>{s.label}</span>
              <span style={{ fontSize: 14, fontWeight: 800, color: scoreColor(s.score) }}>{s.score.toFixed(0)}%</span>
            </div>
            <div style={{ width: "100%", height: 6, background: "oklch(93% 0.01 245)", borderRadius: 999, overflow: "hidden" }}>
              <div style={{ width: `${s.score}%`, height: "100%", background: scoreColor(s.score), borderRadius: 999, transition: "width 1s ease" }} />
            </div>
            <div style={{ fontSize: 11, color: "oklch(45% 0.07 240)", marginTop: 5 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      {/* Word-level breakdown */}
      <div style={{ padding: "4px 22px 16px" }}>
        <div style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.8, fontWeight: 700, color: "oklch(50% 0.05 240)", marginBottom: 8 }}>
          How you read it
        </div>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px 5px",
            lineHeight: 1.8,
            fontSize: 15,
            padding: "14px 16px",
            background: "oklch(99% 0.01 245)",
            border: "1px solid oklch(93% 0.01 245)",
            borderRadius: 12,
          }}
        >
          {p.words.map((w, i) => {
            let color = "oklch(48% 0.18 155)";
            let bg = "transparent";
            let textDecoration = "none";
            let fontWeight = 500;

            if (w.error_type === "omission") {
              color = "oklch(60% 0.1 20)";
              textDecoration = "line-through";
              fontWeight = 400;
            } else if (w.error_type === "insertion") {
              color = "oklch(50% 0.15 45)";
              bg = "oklch(96% 0.05 45)";
              fontWeight = 700;
            } else if (w.error_type === "mispronunciation") {
              color = "oklch(50% 0.15 25)";
              bg = "oklch(96% 0.05 25)";
              fontWeight = 700;
            } else if (w.accuracy_score < 80) {
              color = "oklch(60% 0.13 80)";
              fontWeight = 600;
            }

            return (
              <span
                key={i}
                title={`Accuracy: ${w.accuracy_score}%${w.error_type && w.error_type !== "none" ? ` (${w.error_type})` : ""}`}
                style={{
                  color,
                  backgroundColor: bg,
                  textDecoration,
                  fontWeight,
                  padding: bg !== "transparent" ? "2px 6px" : "0 2px",
                  borderRadius: 4,
                  cursor: "help",
                }}
              >
                {w.word}
              </span>
            );
          })}
        </div>

        {/* Legend */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 16px", fontSize: 11.5, color: "oklch(45% 0.07 240)", marginTop: 8, paddingLeft: 2 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "oklch(48% 0.18 155)" }} />
            <span>Good</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "oklch(60% 0.13 80)" }} />
            <span>Needs work</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "oklch(50% 0.15 25)" }} />
            <span>Mispronounced</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ textDecoration: "line-through", color: "oklch(60% 0.1 20)", fontWeight: 700, fontSize: 12 }}>Aa</span>
            <span>Omitted</span>
          </div>
        </div>
      </div>

    </div>
  );
}

const MAX_RECORD_MS = 60_000;

function StopGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
      <rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" />
    </svg>
  );
}
function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.9s" repeatCount="indefinite" />
      </path>
    </svg>
  );
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function ProgressRing({ progress }: { progress: number }) {
  const size = 36;
  const stroke = 2.5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(1, Math.max(0, progress)));
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{
        position: "absolute",
        inset: 0,
        transform: "rotate(-90deg)",
      }}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="rgba(0,112,196,0.15)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#0070C4"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 200ms linear" }}
      />
    </svg>
  );
}

function subscribeVoiceSupport(onStoreChange: () => void) {
  if (typeof window === "undefined") return () => {};
  const id = window.setTimeout(onStoreChange, 0);
  return () => window.clearTimeout(id);
}

function voiceSupportSnapshot() {
  return isVoiceRecordingSupported();
}

function voiceSupportServerSnapshot() {
  return false;
}

function Composer({
  value,
  onChange,
  onSend,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  placeholder: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const recorder = useVoiceRecorder();
  const voiceSupported = useSyncExternalStore(
    subscribeVoiceSupport,
    voiceSupportSnapshot,
    voiceSupportServerSnapshot,
  );
  const autoStoppedRef = useRef(false);

  const isVoiceBusy =
    recorder.state === "recording" ||
    recorder.state === "transcribing";

  const insertTranscript = (transcript: string) => {
    const clean = transcript.trim();
    if (!clean) return;
    const el = ref.current;
    let next: string;
    let cursorPos: number;
    if (el && typeof el.selectionStart === "number") {
      const start = el.selectionStart;
      const end = el.selectionEnd ?? start;
      const before = value.slice(0, start);
      const after = value.slice(end);
      const needsLeadingSpace = before.length > 0 && !/\s$/.test(before);
      const needsTrailingSpace = after.length > 0 && !/^\s/.test(after);
      const insert =
        (needsLeadingSpace ? " " : "") +
        clean +
        (needsTrailingSpace ? " " : "");
      next = before + insert + after;
      cursorPos = (before + insert).length;
    } else {
      const sep = value.length > 0 && !/\s$/.test(value) ? " " : "";
      next = value + sep + clean;
      cursorPos = next.length;
    }
    onChange(next);
    // Restore cursor on the next tick (after React re-renders).
    requestAnimationFrame(() => {
      if (ref.current) {
        ref.current.focus();
        try {
          ref.current.setSelectionRange(cursorPos, cursorPos);
        } catch {
          /* ignore */
        }
        ref.current.style.height = "auto";
        ref.current.style.height = Math.min(140, ref.current.scrollHeight) + "px";
      }
    });
  };

  const finalizeRecording = useCallback(async () => {
    const blob = await recorder.stop();
    if (!blob || blob.size === 0) {
      recorder.setError("No audio captured. Try again.");
      return;
    }
    recorder.setTranscribing(true);
    try {
      const ext = extensionForMime(recorder.mimeType || "audio/webm");
      const result = await tasksApi.transcribeAudio(blob, `voice${ext}`);
      const transcript = (result.transcript || "").trim();
      if (!transcript) {
        recorder.setError("No speech detected.");
        return;
      }
      insertTranscript(transcript);
      recorder.setTranscribing(false);
    } catch {
      recorder.setError("Couldn't transcribe — try again.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder, value]);

  // Auto-finalize when the 1-minute cap is hit.
  useEffect(() => {
    if (
      recorder.state === "recording" &&
      recorder.elapsedMs >= MAX_RECORD_MS &&
      !autoStoppedRef.current
    ) {
      autoStoppedRef.current = true;
      finalizeRecording();
    }
    if (recorder.state === "idle" || recorder.state === "error") {
      autoStoppedRef.current = false;
    }
  }, [recorder.state, recorder.elapsedMs, finalizeRecording]);

  // Clear an error if the user starts typing.
  useEffect(() => {
    if (recorder.state === "error" && value.length > 0) {
      recorder.setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(140, ref.current.scrollHeight) + "px";
    }
  };

  const handleMicClick = async () => {
    if (recorder.state === "idle" || recorder.state === "error") {
      await recorder.start();
    } else if (recorder.state === "recording") {
      autoStoppedRef.current = true;
      await finalizeRecording();
    }
  };

  const progress = Math.min(1, recorder.elapsedMs / MAX_RECORD_MS);
  const sendDisabled = !value.trim() || isVoiceBusy;

  const micTitle = (() => {
    switch (recorder.state) {
      case "recording": return "Stop recording";
      case "transcribing": return "Transcribing…";
      case "error": return recorder.errorMessage ?? "Try again";
      default: return "Record voice message";
    }
  })();

  return (
    <div style={{
      position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 40,
      padding: "14px 20px 18px",
      background: "linear-gradient(to bottom, rgba(232,240,252,0) 0%, rgba(232,240,252,0.7) 50%, rgba(232,240,252,0.92) 100%)",
      backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
    }}>
      {(isVoiceBusy || recorder.state === "error") && (
        <div style={{
          maxWidth: 720, margin: "0 auto 6px",
          display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8,
          fontSize: 12, color: recorder.state === "error" ? "#c0392b" : "oklch(40% 0.08 240)",
        }}>
          {recorder.state === "error" ? (
            <span>{recorder.errorMessage}</span>
          ) : recorder.state === "transcribing" ? (
            <span>Transcribing…</span>
          ) : (
            <span>{formatElapsed(recorder.elapsedMs)} / 1:00</span>
          )}
        </div>
      )}
      <div style={{
        maxWidth: 720, margin: "0 auto",
        display: "flex", alignItems: "flex-end", gap: 10,
        background: "white", borderRadius: 22,
        padding: "8px 8px 8px 18px",
        border: "1.5px solid rgba(255,255,255,0.92)",
        boxShadow: "0 8px 28px rgba(80,110,180,0.18)",
      }}>
        <textarea
          ref={ref}
          rows={1}
          placeholder={placeholder}
          value={value}
          onChange={handleChange}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!sendDisabled) onSend();
            }
          }}
          style={{
            flex: 1, resize: "none", border: "none", background: "transparent",
            fontSize: 14.5, lineHeight: 1.5, color: "oklch(18% 0.06 240)",
            padding: "9px 0", maxHeight: 140, minHeight: 22,
            fontFamily: "inherit",
            outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {voiceSupported && (
            <div style={{ position: "relative", width: 36, height: 36 }}>
              {recorder.state === "recording" && (
                <ProgressRing progress={progress} />
              )}
              <button
                type="button"
                className="chat-composer-mic-btn"
                data-recording={recorder.state === "recording" ? "true" : "false"}
                onClick={handleMicClick}
                disabled={recorder.state === "transcribing"}
                title={micTitle}
                aria-label={micTitle}
                style={{
                  color: recorder.state === "error" ? "#c0392b" : undefined,
                  cursor: recorder.state === "transcribing" ? "wait" : "pointer",
                }}
              >
                {recorder.state === "transcribing" ? (
                  <Spinner />
                ) : recorder.state === "recording" ? (
                  <StopGlyph />
                ) : (
                  <MicIcon />
                )}
              </button>
            </div>
          )}
          <button
            type="button"
            className="chat-composer-send-btn"
            onClick={onSend}
            disabled={sendDisabled}
            style={{
              cursor: sendDisabled ? "not-allowed" : "pointer",
            }}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Completed-activity compact summary row (resume view) ────────────── */
function CompletedActivityRow({
  summary,
  onRetry,
  retrying,
}: {
  summary: CompletedActivitySummary;
  onRetry: (sequence: number) => void;
  retrying: boolean;
}) {
  const score = Number.isFinite(summary.raw_score) ? summary.raw_score : 0;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 14px",
        marginBottom: 8,
        borderRadius: 14,
        background: "rgba(255,255,255,0.85)",
        border: "1px solid oklch(90% 0.02 245)",
        boxShadow: "0 2px 8px rgba(80,110,180,0.06)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0, flex: 1 }}>
        <Check size={15} style={{ color: "oklch(48% 0.16 155)", flexShrink: 0 }} />
        <span
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "oklch(28% 0.08 245)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          Activity {summary.sequence} · {summary.label}
        </span>
      </div>
      <span
        style={{
          fontSize: 12.5,
          fontWeight: 800,
          color: "oklch(45% 0.07 240)",
          flexShrink: 0,
        }}
      >
        {score.toFixed(1)}/10
      </span>
      <button
        type="button"
        onClick={() => onRetry(summary.sequence)}
        disabled={retrying}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          padding: "5px 11px",
          borderRadius: 999,
          border: "1px solid oklch(86% 0.025 240)",
          background: "white",
          color: "oklch(28% 0.08 245)",
          fontSize: 12,
          fontWeight: 700,
          fontFamily: "inherit",
          cursor: retrying ? "not-allowed" : "pointer",
          opacity: retrying ? 0.55 : 1,
          flexShrink: 0,
        }}
      >
        <RotateCcw size={12} />
        Retry
      </button>
    </div>
  );
}

/* ── Course-completion CTA (shown after the final-day results) ────────── */
function CourseCompletionBanner({ onView }: { onView: () => void }) {
  return (
    <div
      style={{
        marginTop: 20,
        padding: "20px 22px",
        borderRadius: 16,
        background: "oklch(96% 0.05 155)",
        border: "1px solid oklch(82% 0.1 155)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 30, lineHeight: 1 }}>🎉</div>
      <div
        style={{
          fontSize: 16,
          fontWeight: 800,
          color: "oklch(28% 0.12 155)",
        }}
      >
        You&apos;ve completed your course!
      </div>
      <div style={{ fontSize: 13.5, color: "oklch(40% 0.06 200)", lineHeight: 1.6 }}>
        That was your final lesson. Celebrate the milestone and grab your
        certificate.
      </div>
      <button
        type="button"
        onClick={onView}
        style={{
          marginTop: 2,
          padding: "12px 22px",
          borderRadius: 14,
          border: "none",
          background: "#0070C4",
          color: "white",
          fontFamily: "inherit",
          fontSize: 14,
          fontWeight: 800,
          cursor: "pointer",
          boxShadow: "0 6px 18px rgba(0,112,196,0.22)",
        }}
      >
        See your completion
      </button>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────────────────── */
export default function ChatSessionPage() {
  const params = useParams<{ sessionId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const sessionId = params?.sessionId;

  // Course completion is stamped server-side the moment the final-day session
  // completes. Read it off /me so the results screen can offer the completion
  // CTA; the value is refreshed when the session ends (see effect below).
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: authApi.me });
  const courseCompleted = Boolean(me?.preference?.course_completed_at);

  useEffect(() => {
    if (typeof sessionId === "string" && sessionId.length > 0) {
      markDailyChatEntered(sessionId);
    }
  }, [sessionId]);

  const initialConnectionState = useMemo<
    "connecting" | "open" | "closed" | "error"
  >(() => {
    if (typeof window === "undefined") return "connecting";
    return localStorage.getItem("token") ? "connecting" : "error";
  }, []);

  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [composer, setComposer] = useState("");
  const [connectionState, setConnectionState] = useState(initialConnectionState);
  // Server closed the socket with 4402: trial/subscription no longer grants
  // premium access. Suppresses reconnects; the UI offers an upgrade instead.
  const [accessBlocked, setAccessBlocked] = useState(false);
  const [lessonMeta, setLessonMeta] = useState<LessonMeta>({
    title: "Today's lesson",
    focus: "",
    theme: "Lesson",
    cefr: "",
    dayNumber: null,
  });
  const [phase, setPhase] = useState<"teaching" | "practice" | "submitted" | "ended">("teaching");
  const [sessionCompletedByServer, setSessionCompletedByServer] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [loadingType, setLoadingType] = useState<TaskChatLoadingType>(
    initialConnectionState === "connecting" ? "teacher_loading" : null,
  );
  const [loadingTimedOut, setLoadingTimedOut] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [restartDialogOpen, setRestartDialogOpen] = useState(false);
  const [retryingSequence, setRetryingSequence] = useState<number | null>(null);
  // True while a forced task regeneration (retry-on-failed-generation) is in flight.
  const [regenerating, setRegenerating] = useState(false);
  const [currentSequence, setCurrentSequence] = useState<number | null>(null);
  const [lastSubmittedSequence, setLastSubmittedSequence] = useState<number | null>(null);
  const [completedSummaries, setCompletedSummaries] = useState<CompletedActivitySummary[]>([]);
  const [daySessionScorecard, setDaySessionScorecard] =
    useState<SessionScorecardRead | null>(null);
  const [daySessionScorecardError, setDaySessionScorecardError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSendsRef = useRef<WSOutgoing[]>([]);
  const eventsRef = useRef<ChatEvent[]>(events);
  const runtimeBlueprintRef = useRef<RuntimeBlueprint | null>(null);
  // Mirrors `currentSequence` so the stable (`[]`-dep) WS handler can detect
  // when the *just-graded* activity is the last one (→ "completing" skeleton).
  const currentSequenceRef = useRef<number | null>(null);
  // Mirrors `phase` so the stable (`[]`-dep) WS handler can stamp each AI chat
  // bubble's markdown format at creation time — not at render time, which
  // would rebind every past bubble to whatever `phase` currently is.
  const phaseRef = useRef(phase);
  // Set when a restart/retry intentionally wipes the transcript so the next
  // WebSocket open clears non-chat events instead of preserving them.
  const fullResetRef = useRef(false);
  const nextActivityLockRef = useRef(false);
  const reconnectIntentRef = useRef<"none" | "retry" | "auto">("none");
  const [isReconnecting, setIsReconnecting] = useState(false);
  // Consecutive failed auto-reconnects. The ref drives the backoff/cap math
  // synchronously inside callbacks; the state mirror re-renders the CTA.
  const reconnectFailuresRef = useRef(0);
  const [reconnectFailures, setReconnectFailures] = useState(0);

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    currentSequenceRef.current = currentSequence;
  }, [currentSequence]);

  // Hydrate phase + lesson meta from the REST snapshot on mount so a returning
  // learner lands on the correct step without a teaching flash. The WebSocket
  // resume re-delivers the actual transcript/task, so we don't rebuild events
  // here — we only seed phase and, when the day is already done, surface the
  // scorecard immediately.
  useEffect(() => {
    if (typeof sessionId !== "string" || sessionId.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const state = await learningSessionApi.getState(sessionId);
        if (cancelled) return;
        // Compact summaries for completed activities are always refreshed (the
        // WS resume never replays them), including after a restart/retry —
        // hence the `reconnectAttempt` dependency.
        setCompletedSummaries(
          state.daily_completed ? [] : (state.completed_activities ?? []),
        );
        // Phase + current-sequence seeding only matters before the WS resume
        // has populated the transcript; once events exist, the WS is the
        // source of truth and we must not override it.
        if (eventsRef.current.length > 0) return;
        const hydratedResults =
          state.last_resumable_phase === "feedback"
            ? hydrateResultEventsFromState(state)
            : [];
        if (hydratedResults.length > 0) {
          setEvents(hydratedResults);
        }
        if (typeof state.current_sequence === "number") {
          setCurrentSequence(state.current_sequence);
        } else if (hydratedResults.length > 0) {
          const seq = state.completed_sequences?.at(-1);
          if (typeof seq === "number") setCurrentSequence(seq);
        }
        if (reconnectIntentRef.current === "retry") {
          setPhase("practice");
          return;
        }
        const nextPhase =
          state.daily_completed || state.last_resumable_phase === "ended"
            ? "ended"
            : state.last_resumable_phase === "practice_task"
              ? "practice"
              : state.last_resumable_phase === "teaching"
                ? "teaching"
                : state.last_resumable_phase === "feedback"
                  ? "submitted"
                  : "submitted";
        setPhase(nextPhase);
        if (state.daily_completed) setSessionCompletedByServer(true);
      } catch {
        // Snapshot is best-effort; the WebSocket resume is the source of truth.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, reconnectAttempt]);

  useEffect(() => {
    if (phase !== "ended") return;
    // Only fetch the REST fallback when the server confirmed session completion.
    // Skipping this when the user left mid-session (no completed_event received)
    // prevents the spurious "Could not load your session scorecard" error.
    if (!sessionCompletedByServer) return;
    if (typeof sessionId !== "string" || sessionId.length === 0) return;
    if (daySessionScorecard !== null) return;

    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) setDaySessionScorecardError(null);
    });

    const fetchWithRetry = async (url: string, retries = 2): Promise<SessionScorecardRead> => {
      try {
        const r = await api.get<SessionScorecardRead>(url);
        return r.data;
      } catch (err) {
        if (!cancelled && retries > 0) {
          await new Promise((res) => setTimeout(res, 1500));
          return fetchWithRetry(url, retries - 1);
        }
        throw err;
      }
    };

    fetchWithRetry(`/api/learning/sessions/${sessionId}/scorecard`)
      .then((data) => {
        if (cancelled) return;
        setDaySessionScorecard(data);
        markScorecardViewed(data.session_id);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail =
          (err as { response?: { data?: { detail?: string } }; message?: string })
            ?.response?.data?.detail ||
          (err as { message?: string })?.message ||
          "Could not load your session scorecard.";
        setDaySessionScorecardError(detail);
      });

    return () => {
      cancelled = true;
    };
  }, [phase, sessionId, daySessionScorecard, sessionCompletedByServer]);

  // When the server confirms the session is done, refresh /me so a freshly
  // stamped course_completed_at surfaces the completion CTA on this screen.
  useEffect(() => {
    if (sessionCompletedByServer) {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    }
  }, [sessionCompletedByServer, queryClient]);

  useEffect(() => {
    if (phase === "ended") return;
    if (connectionState !== "closed" && connectionState !== "error") return;
    if (typeof sessionId !== "string" || sessionId.length === 0) return;
    if (daySessionScorecard !== null) return;

    let cancelled = false;
    api
      .get<SessionScorecardRead>(`/api/learning/sessions/${sessionId}/scorecard`)
      .then((r) => {
        if (cancelled) return;
        setDaySessionScorecard(r.data);
        markScorecardViewed(r.data.session_id);
        setPhase("ended");
        setLoadingType(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // Only surface the error if the session genuinely has no scorecard yet
        // (i.e. it is still in-progress). For completed sessions the scorecard
        // fetch should always succeed with the corrected URL above.
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status && status !== 404) {
          const detail =
            (err as { response?: { data?: { detail?: string } }; message?: string })
              ?.response?.data?.detail ||
            (err as { message?: string })?.message ||
            "Could not load your session scorecard.";
          setDaySessionScorecardError(detail);
          setPhase("ended");
          setLoadingType(null);
        }
        // 404 = session not yet complete; keep the "connection closed" UI.
      });

    return () => {
      cancelled = true;
    };
  }, [connectionState, phase, sessionId, daySessionScorecard]);

  // Auto-reconnect after ANY drop, in EVERY phase, with capped exponential
  // backoff. (Pre-Phase-4 this only ran during submitted/feedback, so a drop
  // mid-teaching or mid-practice stranded the learner on a dead
  // "Connection closed. Reconnecting…".) On reconnect the backend resume stream
  // rehydrates the transcript + in-progress activity. Once the budget is spent,
  // we stop and let the "Reload session" CTA take over.
  useEffect(() => {
    if (typeof sessionId !== "string" || sessionId.length === 0) return;
    if (
      !shouldScheduleReconnect({
        connectionState,
        accessBlocked,
        exhausted: reconnectExhausted(reconnectFailuresRef.current),
      })
    ) {
      // Budget spent → stop the spinner so the Reload CTA renders.
      if (reconnectExhausted(reconnectFailuresRef.current)) {
        setIsReconnecting(false);
      }
      return;
    }

    const timer = window.setTimeout(() => {
      reconnectFailuresRef.current += 1;
      setReconnectFailures(reconnectFailuresRef.current);
      if (reconnectIntentRef.current === "none") {
        reconnectIntentRef.current = "auto";
      }
      setIsReconnecting(true);
      setConnectionState("connecting");
      setReconnectAttempt((attempt) => attempt + 1);
    }, nextReconnectDelayMs(reconnectFailuresRef.current));

    return () => window.clearTimeout(timer);
  }, [connectionState, accessBlocked, sessionId, reconnectFailures]);

  const LOADING_TIMEOUT_MS = 90_000;

  useEffect(() => {
    if (!loadingType) {
      setLoadingTimedOut(false);
      return;
    }

    setLoadingTimedOut(false);
    const timer = window.setTimeout(() => {
      setLoadingTimedOut(true);
      setLoadingType(null);
    }, LOADING_TIMEOUT_MS);

    return () => window.clearTimeout(timer);
  }, [loadingType, reconnectAttempt]);

  const retryLoadingConnection = useCallback(() => {
    setLoadingTimedOut(false);
    reconnectFailuresRef.current = 0;
    setReconnectFailures(0);
    reconnectIntentRef.current = "auto";
    setIsReconnecting(true);
    setConnectionState("connecting");
    setReconnectAttempt((attempt) => attempt + 1);
  }, []);

  // "Reload session" CTA after the auto-reconnect budget is spent. Resets the
  // budget and forces a fresh connect; bumping reconnectAttempt also re-runs the
  // REST state-hydrate effect, so we re-pull the snapshot and the WS resume
  // replays the in-progress activity — the learner picks up where they were.
  const reloadSession = useCallback(() => {
    reconnectFailuresRef.current = 0;
    setReconnectFailures(0);
    reconnectIntentRef.current = "auto";
    setIsReconnecting(true);
    setConnectionState("connecting");
    setReconnectAttempt((attempt) => attempt + 1);
  }, []);

  const lastTaskIdx = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      if (events[i].kind === "task") return i;
    }
    return -1;
  }, [events]);

  const navigationPromptChatIndex = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const evt = events[i];
      if (
        evt.kind === "chat" &&
        evt.role === "ai" &&
        !evt.streaming &&
        isNavigationPromptActions(evt.actions)
      ) {
        return i;
      }
    }
    return -1;
  }, [events]);

  const firstDayResultsIndex = useMemo(() => {
    const finalIdx = events.findIndex((evt) => evt.kind === "final_scorecard");
    if (finalIdx >= 0) {
      if (finalIdx > 0 && events[finalIdx - 1]?.kind === "section") {
        return finalIdx - 1;
      }
      return finalIdx;
    }
    return -1;
  }, [events]);

  const sessionResultsRef = useRef<HTMLDivElement | null>(null);
  const [dayResultsInView, setDayResultsInView] = useState(false);

  useEffect(() => {
    const el = sessionResultsRef.current;
    if (!el) {
      setDayResultsInView(false);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => setDayResultsInView(entry?.isIntersecting ?? false),
      { threshold: 0.15 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [firstDayResultsIndex, events, phase, daySessionScorecard]);

  const hasCompletionFarewell = useMemo(
    () =>
      events.some(
        (evt) =>
          evt.kind === "chat" &&
          evt.role === "ai" &&
          isNavigationPromptActions(evt.actions) &&
          isDailyCompleteFarewell(evt.content),
      ),
    [events],
  );

  const scrollToDayResults = useCallback(() => {
    sessionResultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const retrySequence = useMemo(() => {
    const fromResults = retrySequenceFromEvents(events);
    if (fromResults !== null) return fromResults;
    if (lastSubmittedSequence !== null) return lastSubmittedSequence;
    if (currentSequence !== null) return currentSequence;
    return latestCompletedSummarySequence(completedSummaries);
  }, [events, lastSubmittedSequence, currentSequence, completedSummaries]);

  const handleIncoming = useCallback((msg: WSIncoming) => {
    // Heartbeat reply — keeps the connection alive; nothing to render.
    if (msg.type === "pong") return;
    if (msg.type === "chat_message") {
      setLoadingType((curr) =>
        shouldShowActivitySkeletonAfterChat(msg.content)
          ? "activity_loading"
          : curr === "teacher_loading" ||
              curr === "next_activity_loading" ||
              curr === "feedback_loading"
            ? null
            : curr,
      );
      if (
        msg.actions?.includes("Go to dashboard") &&
        !msg.actions.includes("Next activity")
      ) {
        setPhase("ended");
      }
      const role = msg.role === "user" || msg.role === "you" ? "you" : "ai";
      setEvents((prev) => [
        ...prev,
        {
          kind: "chat",
          role,
          content: msg.content || "",
          actions: msg.actions,
          format:
            role === "ai" &&
            phaseRef.current === "teaching" &&
            !isNavigationPromptActions(msg.actions)
              ? ("markdown" as const)
              : undefined,
        },
      ]);
      return;
    }
    if (msg.type === "chat_stream_start") {
      setLoadingType((curr) =>
        curr === "teacher_loading" || curr === "next_activity_loading" ? null : curr,
      );
      const streamId = msg.stream_id || `stream-${Date.now()}`;
      const role = msg.role === "user" || msg.role === "you" ? "you" : "ai";
      setEvents((prev) => [
        ...prev,
        {
          kind: "chat",
          role,
          content: "",
          streamId,
          streaming: true,
        },
      ]);
      return;
    }
    if (msg.type === "chat_stream_delta") {
      const streamId = msg.stream_id;
      const delta = msg.content || "";
      if (!streamId || !delta) return;
      setEvents((prev) => {
        let found = false;
        const next = prev.map((evt) => {
          if (evt.kind !== "chat" || evt.streamId !== streamId) return evt;
          found = true;
          return { ...evt, content: evt.content + delta, streaming: true };
        });
        if (found) return next;
        return [
          ...prev,
          {
            kind: "chat",
            role: "ai",
            content: delta,
            streamId,
            streaming: true,
          },
        ];
      });
      return;
    }
    if (msg.type === "chat_stream_end") {
      setLoadingType((curr) =>
        shouldShowActivitySkeletonAfterChat(msg.content)
          ? "activity_loading"
          : curr === "teacher_loading" || curr === "next_activity_loading"
            ? null
            : curr,
      );
      if (
        msg.actions?.includes("Go to dashboard") &&
        !msg.actions.includes("Next activity")
      ) {
        setPhase("ended");
      }
      const streamId = msg.stream_id;
      if (!streamId) {
        if (msg.content) {
          setEvents((prev) => [
            ...prev,
            {
              kind: "chat",
              role: "ai",
              content: msg.content || "",
              actions: msg.actions,
              format:
                phaseRef.current === "teaching" && !isNavigationPromptActions(msg.actions)
                  ? ("markdown" as const)
                  : undefined,
            },
          ]);
        }
        return;
      }
      setEvents((prev) => {
        let found = false;
        const next = prev.map((evt) => {
          if (evt.kind !== "chat" || evt.streamId !== streamId) return evt;
          found = true;
          return {
            ...evt,
            content: msg.content ?? evt.content,
            actions: msg.actions,
            streaming: false,
            format:
              evt.role === "ai" &&
              phaseRef.current === "teaching" &&
              !isNavigationPromptActions(msg.actions)
                ? ("markdown" as const)
                : undefined,
          };
        });
        if (found) return next;
        if (!msg.content) return prev;
        return [
          ...prev,
          {
            kind: "chat",
            role: "ai",
            content: msg.content,
            actions: msg.actions,
            streamId,
            streaming: false,
            format:
              phaseRef.current === "teaching" && !isNavigationPromptActions(msg.actions)
                ? ("markdown" as const)
                : undefined,
          },
        ];
      });
      return;
    }
    if (msg.type === "ui_event") {
      const payloadKind = String(msg.payload?.payload_kind || "");
      if (msg.widget === "session_blueprint" || payloadKind === "session_blueprint") {
        const payload = msg.payload as RuntimeBlueprintPayload;
        const teaching = payload.blueprint?.teaching;
        const sessionMeta = payload._session;
        runtimeBlueprintRef.current = payload.blueprint ?? null;
        setLessonMeta((curr) => ({
          title:
            textValue(teaching?.topic) ||
            textValue(teaching?.lesson_goal) ||
            textValue(teaching?.skill_name) ||
            curr.title,
          focus:
            textValue(teaching?.focus) ||
            textValue(teaching?.lesson_description) ||
            curr.focus,
          theme: displayLabel(textValue(sessionMeta?.theme_type)) || curr.theme,
          cefr: textValue(sessionMeta?.cefr_level) || curr.cefr,
          dayNumber: numberValue(sessionMeta?.day_number) ?? curr.dayNumber,
        }));
        return;
      }
      if (msg.widget === "final_scorecard" || payloadKind === "final_scorecard") {
        setLoadingType(null);
        setSessionCompletedByServer(true);
        const payload = msg.payload as unknown as FinalScorecardPayload;
        setEvents((prev) => [
          ...prev,
          { kind: "section", tone: "score", label: "Final scorecard" },
          { kind: "final_scorecard", payload },
        ]);
        return;
      }
      if (msg.widget === "rag_feedback" || payloadKind === "rag_feedback") {
        const payload = msg.payload as unknown as RagFeedbackPayload;
        // The backend streams a "pending" placeholder first, then a terminal
        // event carrying the real note (or an explicit unavailability). Upsert
        // in place so the placeholder is replaced rather than duplicated, and
        // always render — never silently drop the card when the note is absent.
        setEvents((prev) => {
          const idx = prev.map((e) => e.kind).lastIndexOf("rag_feedback");
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = { kind: "rag_feedback", payload };
            return next;
          }
          return [
            ...prev,
            { kind: "section", tone: "feedback", label: "Coach note" },
            { kind: "rag_feedback", payload },
          ];
        });
        return;
      }
      if (msg.widget === "session_completed" || payloadKind === "completed") {
        // Final scorecard + RAG feedback render inline; the farewell chat
        // with "Go to dashboard" follows and drives phase → ended.
        setLoadingType(null);
        setSessionCompletedByServer(true);
        return;
      }
      if (msg.widget === "pronunciation_result") {
        const seq = sequenceFromMeta(msg.payload);
        // Pronunciation is a single combined card; if it's the final activity,
        // hold the completion (final scorecard + coach) skeletons next.
        setLoadingType(
          isLastActivitySequence(runtimeBlueprintRef.current, seq) ? "completing" : null,
        );
        const payload = msg.payload as unknown as PronunciationResultPayload;
        setCurrentSequence(seq);
        setEvents((prev) => [
          ...prev,
          { kind: "section", tone: "score", label: "Pronunciation assessment" },
          { kind: "pronunciation", payload },
        ]);
        nextActivityLockRef.current = false;
        setPhase("submitted");
        return;
      }
      if (msg.widget === "scorecard" || payloadKind === "evaluation") {
        setLoadingType("feedback_loading");
        const payload = msg.payload as unknown as ScorecardPayload;
        setCurrentSequence(sequenceFromMeta(msg.payload));
        setLessonMeta((curr) => ({
          ...curr,
          title: curr.title === "Today's lesson" ? payload.topic || curr.title : curr.title,
          theme: curr.theme === "Lesson" ? displayLabel(payload.skill_name || "") || curr.theme : curr.theme,
        }));
        setEvents((prev) => [
          ...prev,
          { kind: "section", tone: "score", label: "Activity score" },
          { kind: "scorecard", payload },
        ]);
        nextActivityLockRef.current = false;
        setPhase("submitted");
        return;
      }
      if (msg.widget === "feedback_card" || payloadKind === "feedback") {
        // After the last activity's feedback, hold the completion skeletons
        // (final scorecard + coach) until the server emits those events. The
        // graded sequence comes from the scorecard event that always precedes
        // feedback (mirrored into currentSequenceRef).
        setLoadingType(
          isLastActivitySequence(runtimeBlueprintRef.current, currentSequenceRef.current)
            ? "completing"
            : null,
        );
        const payload = msg.payload as unknown as FeedbackPayload;
        setEvents((prev) => [
          ...prev,
          { kind: "section", tone: "feedback", label: "Activity feedback" },
          { kind: "feedback", payload },
        ]);
        return;
      }

      const widget = normalizeWidgetKey(
        String(
          (msg.payload?.task_widget as string | undefined) ||
          (msg.payload?.widget as string | undefined) ||
          msg.widget,
        ),
      );
      if (isKnownWidget(widget)) {
        setLoadingType(null);
        const activityContract = findRuntimeActivityContract(
          runtimeBlueprintRef.current,
          msg.payload,
        );
        const payload = {
          ...msg.payload,
          blueprint_contract: activityContract ?? undefined,
          widget,
        } as unknown as AnyTaskPayload;
        const topicName =
          (payload as { topic_name?: string; topic?: string }).topic_name ||
          (payload as { topic_name?: string; topic?: string }).topic ||
          "";
        if (topicName) {
          setLessonMeta((curr) => ({
            ...curr,
            title: curr.title === "Today's lesson" ? topicName : curr.title,
          }));
        }
        setCurrentSequence(sequenceFromMeta(msg.payload));
        // A task arrived — any in-flight regeneration succeeded.
        setRegenerating(false);
        setEvents((prev) => [
          ...prev,
          { kind: "section", tone: "task", label: WIDGET_SECTION_LABEL[widget] },
          { kind: "task", payload, submitted: false, answers: {} },
        ]);
        setPhase("practice");
        return;
      }
      // Unknown widget — surface as a chat message so the session doesn't get stuck silently.
      setLoadingType(null);
      setEvents((prev) => [
        ...prev,
        {
          kind: "chat",
          role: "ai",
          content: `This activity uses the ${msg.widget.replace(/_/g, " ")} widget, which isn't supported yet.`,
        },
      ]);
      return;
    }
    if (msg.type === "error") {
      setLoadingType(null);
      setRegenerating(false);
      // A recoverable task-generation/validation failure (tagged by the backend)
      // gets a retry icon next to the copy icon; the learner can force a fresh
      // generation. Other errors stay as a plain warning with no retry.
      const recoverable = msg.code === "task_generation_failed";
      setEvents((prev) => [
        ...prev,
        {
          kind: "chat",
          role: "ai",
          content: `⚠️ ${msg.content || "Something went wrong."}`,
          retryTaskGen: recoverable,
        },
      ]);
    }
  }, []);

  /* --- WebSocket lifecycle ---------------------------------------- */
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let socket: WebSocket | null = null;
    let heartbeat: ReturnType<typeof setInterval> | undefined;

    const clearHeartbeat = () => {
      if (heartbeat !== undefined) {
        clearInterval(heartbeat);
        heartbeat = undefined;
      }
    };

    void (async () => {
      let token =
        typeof window !== "undefined" ? localStorage.getItem("token") : null;
      // On a reconnect (not the initial mount) refresh the JWT FIRST: a session
      // running past the 20-min access-token TTL would otherwise present an
      // expired token and be 4401-closed forever. The first connect uses the
      // freshly-minted login token as-is (no extra round-trip).
      if (reconnectAttempt > 0) {
        try {
          token = await refreshAccessToken();
          useAuthStore.getState().setToken(token);
        } catch {
          // Refresh failed (refresh cookie also gone). Fall back to the stored
          // token; a resulting 4401 surfaces via the reconnect budget → CTA.
        }
      }
      if (cancelled || !token) return;

      const ws = new WebSocket(buildLearningWsUrl(WS_BASE_URL, sessionId, token));
      socket = ws;
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        reconnectIntentRef.current = "none";
        reconnectFailuresRef.current = 0;
        setReconnectFailures(0);
        setIsReconnecting(false);
        setConnectionState("open");
        setLoadingType((curr) => curr ?? (eventsRef.current.length === 0 ? "teacher_loading" : null));
        // Heartbeat: ping under the ALB's 120s idle window so a reading/thinking
        // lull never drops the socket. The server pongs (ignored on receipt).
        clearHeartbeat();
        heartbeat = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, HEARTBEAT_INTERVAL_MS);
        // The backend resume re-sends the blueprint and the live task widget on
        // every (re)connect. Drop only the stale live task to avoid duplicates,
        // but keep already-delivered results (scorecards/feedback) and the chat
        // transcript so an in-app reconnect doesn't lose the screen. A confirmed
        // restart/retry wipes everything (it already cleared events), so honour
        // that by filtering to chat-only.
        if (fullResetRef.current) {
          fullResetRef.current = false;
          setEvents((prev) => prev.filter((e) => e.kind === "chat"));
        } else {
          setEvents((prev) => prev.filter((e) => e.kind !== "task"));
        }
        const queued = pendingSendsRef.current.splice(0);
        queued.forEach((payload) => ws.send(JSON.stringify(payload)));
      };
      ws.onclose = (event) => {
        if (wsRef.current !== ws) return;
        clearHeartbeat();
        if (event.code === 4402) {
          setAccessBlocked(true);
          setConnectionState("error");
          setLoadingType(null);
          return;
        }
        // Mark closed whether this was a fresh drop OR a failed reconnect
        // attempt (intent still "auto"/"retry"). The reconnect effect then
        // retries with backoff, or surfaces the Reload CTA once the budget is
        // spent. The old `intent !== "none"` early-return is exactly what left a
        // failed reconnect stuck on a permanent "Reconnecting…".
        setConnectionState("closed");
        setLoadingType(null);
      };
      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        clearHeartbeat();
        setConnectionState("error");
        setLoadingType(null);
      };

      ws.onmessage = (raw) => {
        if (wsRef.current !== ws) return;
        try {
          const msg = JSON.parse(raw.data) as WSIncoming;
          handleIncoming(msg);
        } catch (err) {
          console.error("Bad WS payload", err);
        }
      };
    })();

    return () => {
      cancelled = true;
      clearHeartbeat();
      if (socket) {
        socket.close();
        if (wsRef.current === socket) wsRef.current = null;
      }
    };
  }, [sessionId, handleIncoming, reconnectAttempt]);

  const send = useCallback((payload: WSOutgoing) => {
    // This local loading phase mirrors WebSocket waits only; backend session phase remains authoritative.
    if (payload.type === "task_submission") {
      // Score arrives first (backend emits the scorecard the moment grading
      // finishes — Workstream A), so reserve the score slot now; the scorecard
      // event advances this to the feedback skeleton.
      setLoadingType("evaluation_loading");
    } else if (payload.type === "follow_up_action") {
      setLoadingType(
        payload.action.trim().toLowerCase() === "next activity"
          ? "next_activity_loading"
          : "teacher_loading",
      );
    } else {
      setLoadingType("teacher_loading");
    }
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return;
    }
    pendingSendsRef.current.push(payload);
    setConnectionState("connecting");
    setReconnectAttempt((attempt) => attempt + 1);
  }, []);

  function handleSendComposer() {
    const trimmed = composer.trim();
    if (!trimmed) return;

    if (phase === "submitted" || phase === "ended") {
      setEvents((prev) => [...prev, { kind: "chat", role: "you", content: trimmed }]);
      send({ type: "follow_up_action", action: trimmed });
    } else {
      setEvents((prev) => [...prev, { kind: "chat", role: "you", content: trimmed }]);
      send({ type: "user_message", content: trimmed });
    }
    setComposer("");
  }

  function handleAction(label: string) {
    if (label === "Go to dashboard") {
      router.push("/dashboard");
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["task", "next"] });
        queryClient.invalidateQueries({ queryKey: ["me"] });
      }, 0);
      return;
    }
    if (label === RETRY_ACTIVITY_ACTION) {
      // Pass-mark gate: re-run the activity the learner just failed. Reuse the
      // existing reset → reconnect → resume path (backend re-delivers the now
      // PENDING attempt). Sequence comes from the live task or, as a fallback,
      // the most recent scorecard/pronunciation event.
      const seq = currentSequence ?? retrySequenceFromEvents(events);
      if (seq !== null && retryingSequence === null) {
        setEvents((prev) => [...prev, { kind: "chat", role: "you", content: label }]);
        void handleRetryActivity(seq);
      }
      return;
    }
    if (
      label === "Next activity" &&
      (nextActivityLockRef.current ||
        phase === "practice" ||
        loadingType === "next_activity_loading")
    ) {
      return;
    }
    if (label === "Next activity") {
      nextActivityLockRef.current = true;
    }
    setEvents((prev) => [...prev, { kind: "chat", role: "you", content: label }]);
    send({ type: "follow_up_action", action: label });
    if (label === "Next activity") setPhase("practice");
  }

  function handleRegenerateTask() {
    if (regenerating) return;
    // Force a brand-new task generation on the backend (it bypasses the broken
    // cached content and re-runs the task agent), then re-delivers the task.
    setRegenerating(true);
    send({ type: "follow_up_action", action: REGENERATE_TASK_ACTION });
  }

  function requestRestartSession() {
    if (!sessionId || restarting) return;
    setRestartDialogOpen(true);
  }

  async function confirmRestartSession() {
    if (!sessionId || restarting) return;

    setRestarting(true);
    setLoadingType("teacher_loading");
    try {
      const restartPath = `/api/learning/sessions/${encodeURIComponent(sessionId)}/restart`;
      const res = await api.post<{
        session_id: string;
        topic: string;
        skill_name: string;
        task_type: string;
        user_task_id?: number | null;
        message: string;
      }>(restartPath);

      fullResetRef.current = true;
      nextActivityLockRef.current = false;
      pendingSendsRef.current = [];
      wsRef.current?.close();
      wsRef.current = null;
      setEvents([]);
      setComposer("");
      setCurrentSequence(null);
      setLastSubmittedSequence(null);
      setCompletedSummaries([]);
      // Restart wipes the V2 scorecard server-side; drop the cached copy so a
      // later re-completion refetches fresh scores instead of the stale guard
      // short-circuiting the refetch.
      setDaySessionScorecard(null);
      setDaySessionScorecardError(null);
      setSessionCompletedByServer(res.data.message === "Session complete");
      setPhase(res.data.message === "Session complete" ? "ended" : "teaching");
      setLessonMeta((curr) => ({
        ...curr,
        title: res.data.topic || "Today's lesson",
        theme: displayLabel(res.data.skill_name || "") || curr.theme,
        focus: "",
      }));
      setConnectionState("connecting");
      setReconnectAttempt((attempt) => attempt + 1);
      markDailyChatEntered(res.data.session_id);
      queryClient.invalidateQueries({ queryKey: ["task", "next"] });
      setRestartDialogOpen(false);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail ||
        (err as { message?: string })?.message ||
        "Could not restart this session.";
      setLoadingType(null);
      setEvents((prev) => [
        ...prev,
        { kind: "chat", role: "ai", content: detail },
      ]);
      setRestartDialogOpen(false);
    } finally {
      setRestarting(false);
    }
  }

  async function handleRetryActivity(sequence: number) {
    if (!sessionId || retryingSequence !== null) return;
    setRetryingSequence(sequence);
    setLoadingType("activity_loading");
    try {
      await learningSessionApi.resetActivity(sessionId, sequence);
      // Wipe the transcript back to the teaching/chat history; the backend
      // resume re-delivers the reset activity as the live task on reconnect.
      fullResetRef.current = true;
      nextActivityLockRef.current = false;
      reconnectIntentRef.current = "retry";
      setIsReconnecting(true);
      pendingSendsRef.current = [];
      wsRef.current?.close();
      wsRef.current = null;
      setEvents([]);
      setComposer("");
      setDaySessionScorecard(null);
      setDaySessionScorecardError(null);
      setCurrentSequence(null);
      setLastSubmittedSequence(null);
      setPhase("practice");
      setConnectionState("connecting");
      setReconnectAttempt((attempt) => attempt + 1);
      queryClient.invalidateQueries({ queryKey: ["task", "next"] });
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail ||
        (err as { message?: string })?.message ||
        "Could not retry this activity.";
      setLoadingType(null);
      setIsReconnecting(false);
      reconnectIntentRef.current = "none";
      setEvents((prev) => [...prev, { kind: "chat", role: "ai", content: `⚠️ ${detail}` }]);
    } finally {
      setRetryingSequence(null);
    }
  }

  const setTaskAnswers = useCallback((eventIdx: number, next: Record<string, unknown>) => {
    setEvents((prev) =>
      prev.map((e, i) =>
        i === eventIdx && e.kind === "task" ? { ...e, answers: next } : e,
      ),
    );
  }, []);

  const handleSubmitTask = useCallback((
    eventIdx: number,
    answersOverride?: Record<string, unknown>,
  ) => {
    const evt = eventsRef.current[eventIdx];
    if (!evt || evt.kind !== "task" || evt.submitted) return;
    const answers = answersOverride ?? evt.answers ?? {};
    const submittedSequence =
      currentSequence ?? sequenceFromMeta(evt.payload as Record<string, unknown>);
    if (submittedSequence !== null) setLastSubmittedSequence(submittedSequence);
    send({ type: "task_submission", answers });
    setEvents((prev) =>
      prev.map((e, i) =>
        i === eventIdx && e.kind === "task"
          ? { ...e, submitted: true, answers }
          : e,
      ),
    );
    setPhase("submitted");
  }, [send, currentSequence]);

  /* --- Render ----------------------------------------------------- */
  const composerPlaceholder =
    phase === "teaching" ? "Type your answer…"
    : phase === "practice" ? "Use the task above…"
    : "Ask a follow-up question…";

  const hasActiveAiStream = events.some(
    (evt) => evt.kind === "chat" && evt.role === "ai" && evt.streaming,
  );
  // The compact completed-activity rows are a *resume* affordance. Once the
  // live transcript already shows result widgets (the learner has been working
  // in this session), suppress the rows so a mid-session reconnect — which
  // preserves those widgets — can't render the same activity both inline and
  // as a compact row.
  const hasInlineResults = events.some(
    (evt) =>
      evt.kind === "scorecard" ||
      evt.kind === "feedback" ||
      evt.kind === "pronunciation" ||
      evt.kind === "final_scorecard",
  );
  // The score/feedback/completion skeletons don't need a result-existence
  // guard: each real event's handler advances `loadingType` atomically when it
  // appends its widget, so the trailing skeleton is replaced in place. Only the
  // teacher skeleton needs suppression — it's set on connect and an active
  // stream bubble already covers that slot. (A global result check would
  // wrongly suppress every activity after the first, since the transcript is
  // append-only and keeps prior results.)
  const visibleLoadingType: TaskChatLoadingType =
    loadingType === "teacher_loading" && hasActiveAiStream ? null : loadingType;
  // Deterministic label for the trailing task skeleton (next activity in the
  // blueprint), so its section marker matches the real task event that replaces it.
  const skeletonTaskLabel = nextActivitySkeletonLabel(runtimeBlueprintRef.current, currentSequence);
  const hasLiveTask = events.some((evt) => evt.kind === "task");
  const hasFinalScorecard = events.some((evt) => evt.kind === "final_scorecard");
  const showScrollToDayResults =
    !dayResultsInView &&
    (hasFinalScorecard
      ? firstDayResultsIndex >= 0 && hasCompletionFarewell
      : phase === "ended" && Boolean(daySessionScorecard));
  const showTeachingMarker =
    phase === "teaching" &&
    !hasLiveTask &&
    !hasInlineResults &&
    !visibleLoadingType &&
    connectionState === "open";
  // Surface a connection notice whenever the socket isn't open and there is no
  // loading skeleton already covering it. Unlike before, we no longer suppress
  // it during `isReconnecting` — an active recovery now shows a calm
  // "Reconnecting…", and a spent budget shows the "Reload session" CTA, instead
  // of a silent dead-end.
  const reconnectIsExhausted = reconnectExhausted(reconnectFailures);
  const showConnectionIssue =
    connectionState !== "open" && phase !== "ended" && !visibleLoadingType;

  return (
    <>
      <ChatGlobalStyles />

      <ChatPageShell>
        <Topbar
          onRestart={requestRestartSession}
          restarting={restarting}
          onRestartActivity={() => {
            const sequence =
              phase === "practice" && currentSequence !== null
                ? currentSequence
                : retrySequence;
            if (sequence !== null) void handleRetryActivity(sequence);
          }}
          canRestartActivity={
            (phase === "practice" && currentSequence !== null) ||
            (navigationPromptChatIndex >= 0 && retrySequence !== null)
          }
          restartingActivity={retryingSequence !== null}
        />

        <AppConfirmDialog
          open={restartDialogOpen}
          title="Restart this session?"
          description="This clears today's activity progress and scores for this session and starts over from teaching."
          confirmLabel="Restart session"
          loadingLabel="Restarting..."
          isLoading={restarting}
          tone="warning"
          onCancel={() => setRestartDialogOpen(false)}
          onConfirm={confirmRestartSession}
        />

        <ChatMain bottomPadding={200}>
          <LessonMetaCard
            eyebrow={buildLessonEyebrow(lessonMeta)}
            title={lessonMeta.title}
            focus={lessonMeta.focus}
          />

          {showTeachingMarker && (
            <SectionMarker tone="intro" icon={<MessageCircle size={13} />}>
              Teaching
            </SectionMarker>
          )}

          {phase !== "ended" && !hasInlineResults && completedSummaries.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <SectionMarker tone="score" icon={<Sparkles size={13} />}>
                Completed activities
              </SectionMarker>
              {completedSummaries.map((summary) => (
                <CompletedActivityRow
                  key={summary.sequence}
                  summary={summary}
                  onRetry={handleRetryActivity}
                  retrying={retryingSequence !== null}
                />
              ))}
            </div>
          )}

          {events.map((evt, i) => {
            if (evt.kind === "chat") {
              if (
                hasFinalScorecard &&
                evt.role === "ai" &&
                !evt.streaming &&
                isNavigationPromptActions(evt.actions) &&
                !isDailyCompleteFarewell(evt.content)
              ) {
                return null;
              }
              const isNavigationPrompt =
                evt.role === "ai" &&
                !evt.streaming &&
                isNavigationPromptActions(evt.actions);
              const hasExplicitRetry = (evt.actions ?? []).includes(
                RETRY_ACTIVITY_ACTION,
              );
              const showRetry =
                isNavigationPrompt &&
                i === navigationPromptChatIndex &&
                retrySequence !== null &&
                !hasExplicitRetry;
              const isLatestNavigationPrompt =
                isNavigationPrompt && i === navigationPromptChatIndex;
              const useFormatted =
                evt.role === "ai" &&
                !evt.streaming &&
                !isNavigationPrompt &&
                evt.format === "markdown";
              return (
                <ChatBubble
                  key={i}
                  role={evt.role}
                  name={i === 0 && evt.role === "ai" ? "LingosAI" : undefined}
                  actions={isNavigationPrompt ? navigationPromptActions(evt.actions) : evt.actions}
                  streaming={evt.streaming}
                  onAction={
                    isLatestNavigationPrompt
                      ? handleAction
                      : isNavigationPrompt
                        ? (actionLabel) => {
                            if (actionLabel === "Go to dashboard") handleAction(actionLabel);
                          }
                        : handleAction
                  }
                  copyText={evt.role === "ai" ? evt.content : undefined}
                  onRetry={
                    evt.retryTaskGen
                      ? handleRegenerateTask
                      : showRetry
                        ? () => handleRetryActivity(retrySequence)
                        : undefined
                  }
                  retrying={
                    evt.retryTaskGen ? regenerating : retryingSequence !== null
                  }
                >
                  {useFormatted ? (
                    <ChatFormattedText>{evt.content}</ChatFormattedText>
                  ) : (
                    evt.content
                  )}
                </ChatBubble>
              );
            }
            if (evt.kind === "section") {
              const anchorResults = i === firstDayResultsIndex;
              return (
                <div
                  key={i}
                  ref={anchorResults ? sessionResultsRef : undefined}
                  id={anchorResults ? "session-day-results" : undefined}
                >
                  <SectionMarker
                    tone={evt.tone}
                    icon={evt.tone === "task" ? <FileText size={13} /> : <Sparkles size={13} />}
                  >
                    {evt.label}
                  </SectionMarker>
                </div>
              );
            }
            if (evt.kind === "task") {
              const widget = evt.payload.widget;
              const richTask = adaptContractTask(evt.payload);
              if (richTask) {
                return (
                  <TaskWidgetRenderer
                    key={i}
                    task={richTask}
                    previewState="default"
                    live={{
                      answers: evt.answers,
                      setAnswers: (next) => setTaskAnswers(i, next),
                      onSubmit: (answers) => handleSubmitTask(i, answers),
                      submitted: evt.submitted,
                    }}
                  />
                );
              }
              const rawTaskWidget = rawContractTaskWidget(evt.payload);
              if (rawTaskWidget && process.env.NODE_ENV !== "production") {
                return (
                  <ChatBubble key={i} role="ai">
                    <span style={{ color: "#cf2e2e", fontWeight: 800 }}>
                      ⚠ Dev: task_widget &ldquo;{rawTaskWidget}&rdquo; did not converge to the rich
                      widget library (fell back to the generic widget). Add it to CONVERGED_WIDGETS
                      + adaptContractTask.
                    </span>
                  </ChatBubble>
                );
              }
              const Widget = WIDGET_COMPONENTS[widget];
              if (!Widget) {
                return (
                  <ChatBubble key={i} role="ai">
                    This activity uses the {widget.replace(/_/g, " ")} widget, which isn&apos;t supported yet.
                  </ChatBubble>
                );
              }
              return (
                <Widget
                  key={i}
                  payload={evt.payload}
                  answers={evt.answers}
                  setAnswers={(next) => setTaskAnswers(i, next)}
                  state={evt.submitted ? "after" : "before"}
                  onSubmit={(answers) => handleSubmitTask(i, answers)}
                />
              );
            }
            if (evt.kind === "scorecard") {
              const lastTask = events.slice(0, i).reverse().find((e) => e.kind === "task");
              return (
                <RuntimeEvaluationCard
                  key={i}
                  scorecard={evt.payload}
                  taskPayload={lastTask?.kind === "task" ? lastTask.payload : null}
                  taskAnswers={lastTask?.kind === "task" ? lastTask.answers : undefined}
                />
              );
            }
            if (evt.kind === "final_scorecard") {
              const anchorResults =
                i === firstDayResultsIndex &&
                (firstDayResultsIndex === 0 ||
                  events[firstDayResultsIndex - 1]?.kind !== "section");
              return (
                <div
                  key={i}
                  ref={anchorResults ? sessionResultsRef : undefined}
                  id={anchorResults ? "session-day-results" : undefined}
                >
                  <RuntimeFinalScorecard payload={evt.payload} />
                </div>
              );
            }
            if (evt.kind === "rag_feedback") {
              // The "pending" placeholder holds the coach slot with a
              // shape-matched skeleton (the "Coach note" section marker is
              // already appended ahead of this event) until the real note lands.
              if (evt.payload.pending) return <CoachSkeleton key={i} />;
              return <RuntimeRagFeedback key={i} payload={evt.payload} />;
            }
            if (evt.kind === "feedback") {
              const lastTask = events.slice(0, i).reverse().find((e) => e.kind === "task");
              const gate = evt.payload.gate;
              return (
                <div key={i}>
                  {gate && !gate.passed && (
                    <PassMarkBanner
                      scorePct={gate.score_pct}
                      thresholdPct={gate.threshold_pct}
                    />
                  )}
                  <RuntimeFeedbackCard
                    feedback={evt.payload}
                    taskPayload={lastTask?.kind === "task" ? lastTask.payload : null}
                  />
                </div>
              );
            }
            if (evt.kind === "pronunciation") {
              return <ChatPronunciationCard key={i} payload={evt.payload} />;
            }
            return null;
          })}

          <TaskChatLoadingSkeleton type={visibleLoadingType} taskLabel={skeletonTaskLabel} />

          {loadingTimedOut && (
            <div style={{ marginTop: 16 }}>
              <ChatBubble role="ai">
                This is taking longer than expected. Try reconnecting to resume your session.
              </ChatBubble>
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={retryLoadingConnection}
                  style={{
                    borderRadius: 999,
                    border: "1px solid oklch(82% 0.03 240)",
                    background: "white",
                    padding: "8px 14px",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  Reconnect
                </button>
              </div>
            </div>
          )}

          {showConnectionIssue && (
            <ReconnectNotice
              connectionState={connectionState}
              accessBlocked={accessBlocked}
              isReconnecting={isReconnecting}
              exhausted={reconnectIsExhausted}
              labelAsLingos={events.length === 0}
              onReload={reloadSession}
            />
          )}

          {phase === "ended" && !hasFinalScorecard && sessionCompletedByServer && (
            <div
              ref={sessionResultsRef}
              id="session-day-results"
              style={{ marginTop: 24 }}
            >
              {daySessionScorecard ? (
                <DaySessionScorecard
                  scorecard={daySessionScorecard}
                  onGoToDashboard={() => {
                    queryClient.invalidateQueries({ queryKey: ["sessions", "today-plan"] });
                    queryClient.invalidateQueries({ queryKey: ["me"] });
                    router.push("/dashboard");
                  }}
                />
              ) : daySessionScorecardError ? (
                <ChatBubble role="ai">
                  Could not load your session scorecard: {daySessionScorecardError}
                </ChatBubble>
              ) : (
                <ChatBubble role="ai">Loading your session scorecard…</ChatBubble>
              )}
            </div>
          )}

          {courseCompleted && (sessionCompletedByServer || hasFinalScorecard) && (
            <CourseCompletionBanner onView={() => router.push("/course-complete")} />
          )}

          <div style={{ height: 60 }} />
        </ChatMain>

        {showScrollToDayResults && (
          <button
            type="button"
            aria-label="View your session score and coach feedback"
            onClick={scrollToDayResults}
            style={{
              position: "fixed",
              bottom: 92,
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 20,
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: "1px solid oklch(82% 0.03 240)",
              background: "white",
              color: "oklch(42% 0.12 240)",
              boxShadow: "0 8px 24px rgba(35,55,100,0.18)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
            }}
          >
            <ChevronDown size={22} strokeWidth={2.4} />
          </button>
        )}

        <Composer
          value={composer}
          onChange={setComposer}
          onSend={handleSendComposer}
          placeholder={composerPlaceholder}
        />
        {/* lastTaskIdx is exposed for future scroll-into-view; keeps lint quiet */}
        <span data-last-task={lastTaskIdx} style={{ display: "none" }} />
      </ChatPageShell>
    </>
  );
}
