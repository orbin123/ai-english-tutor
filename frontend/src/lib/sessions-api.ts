/**
 * Typed client for the daily-sessions REST API.
 *
 * Backend mounts the routes under `/api/sessions`.
 */

import { api } from "./api";

// ── Status enums (must match backend exactly) ──────────────────────

export type SessionStatus = "in_progress" | "completed" | "abandoned";
export type AttemptStatus = "pending" | "submitted" | "evaluated";
export type CourseLength = "24w" | "48w";

// ── Schemas ────────────────────────────────────────────────────────

export interface ActivityPreferences {
  allow_read?: boolean;
  allow_write?: boolean;
  allow_listen?: boolean;
  allow_speak?: boolean;
}

export interface SessionStartRequest {
  day_id: string;
  course_length: CourseLength;
  tasks_per_day: 2 | 3 | 4;
  preferences?: ActivityPreferences;
}

export interface AttemptSkeleton {
  sequence: number;
  archetype_id: string;
  archetype_name: string;
  is_mandatory: boolean;
  status: AttemptStatus;
}

export interface DashboardPlanActivity {
  sequence: number;
  archetype_id: string;
  archetype_name: string;
  core_activity: "read" | "write" | "listen" | "speak";
  ui_widget: string;
  is_mandatory: boolean;
  status: AttemptStatus;
}

export interface DashboardTodayPlanResponse {
  day_id: string;
  topic: string;
  session_id: string | null;
  status: SessionStatus | null;
  is_preview: boolean;
  activities: DashboardPlanActivity[];
  /** File-authored fields — prefer over DB when present. */
  explanation_brief: string | null;
  cefr_level: string | null;
  course_length: string | null;
  /** True only on 48w even-pass (depth) days. */
  is_depth_day: boolean;
}

export interface DashboardStartResponse extends DashboardTodayPlanResponse {
  mode: "start" | "continue" | "completed";
}

export interface SessionStartResponse {
  session_id: string;
  day_id: string;
  course_length: CourseLength;
  status: SessionStatus;
  is_first_attempt: boolean;
  started_at: string;
  attempts: AttemptSkeleton[];
}

export interface NextActivityResponse {
  sequence: number;
  archetype_id: string;
  is_mandatory: boolean;
  status: AttemptStatus;
  ui_widget: string;
  task_content: Record<string, unknown>;
}

export interface SubmitActivityRequest {
  user_response: Record<string, unknown>;
}

export interface MistakeRead {
  user_wrote?: string | null;
  issue: string;
  correction?: string | null;
  rule?: string | null;
  sub_skills_affected: string[];
}

export interface FeedbackRead {
  score: number;
  summary: string;
  did_well: string[];
  mistakes: MistakeRead[];
  next_tip: string | null;
  sub_skill_breakdown: Record<string, number>;
}

export interface EvaluationRead {
  raw_score: number;
  rubric_scores: Record<string, number>;
  base_reward: number;
  weighted_points: Record<string, number>;
  evaluator_notes: string | null;
}

export interface SubmitActivityResponse {
  sequence: number;
  status: AttemptStatus;
  evaluation: EvaluationRead;
  feedback: FeedbackRead;
}

export interface ActivityBreakdown {
  attempt_id: number;
  sequence: number;
  archetype_id: string;
  archetype_label: string;
  raw_score: number;
  tier: string;
  base_reward: number;
  weighted_points: Record<string, number>;
}

export interface SessionScorecardRead {
  session_id: string;
  points_earned: Record<string, number>;
  subskill_totals_after: Record<string, number>;
  dashboard_after: Record<string, number>;
  skill_labels: Record<string, string>;
  completed_at: string;
  points_applied: boolean;
  activities: ActivityBreakdown[];
  mentor_note?: string | null;
  // The scorecard's own id — the COACH_NOTE reaction target (feedback_id).
  scorecard_id?: number | null;
  // The viewer's reaction to the Coach's Note ("LIKE"/"DISLIKE"/null).
  user_reaction?: "LIKE" | "DISLIKE" | null;
}

export interface AdvanceDayResponse {
  week: number;
  day_in_week: number;
}

// ── Learning (chat) session hydrate state ──────────────────────────

export interface CompletedActivitySummary {
  sequence: number;
  archetype_id: string;
  label: string;
  archetype_label: string;
  widget: string;
  raw_score: number;
}

export interface LearningSessionState {
  session_id: string;
  daily_session_id: number;
  topic: string;
  skill_name: string;
  task_type: string;
  phase: string;
  messages: Array<Record<string, unknown>>;
  task_queue: Array<Record<string, unknown>>;
  current_task: Record<string, unknown> | null;
  current_sequence: number | null;
  last_evaluation: Record<string, unknown> | null;
  last_feedback: Record<string, unknown> | null;
  completed_sequences: number[];
  completed_activities: CompletedActivitySummary[];
  teaching_completed: boolean;
  last_resumable_phase: string;
  daily_completed: boolean;
  blueprint: Record<string, unknown> | null;
}

export interface LearningRestartResponse {
  session_id: string;
  daily_session_id: number;
  topic: string;
  skill_name: string;
  task_type: string;
  message: string;
}

export interface RegenerateFeedbackResponse {
  sequence: number;
  // Same shape as the WS `feedback_card` payload; the chat page casts it to its
  // FeedbackPayload before swapping into the rendered card.
  feedback: Record<string, unknown>;
}

export interface PronunciationResult {
  overall_score: number;
  accuracy_score: number;
  fluency_score: number;
  completeness_score: number;
  prosody_score?: number;
  words: {
    word: string;
    accuracy_score: number;
    error_type: string;
    phonemes: {
      phoneme: string;
      accuracy_score: number;
    }[];
  }[];
}

// ── Endpoints ──────────────────────────────────────────────────────

export const sessionsApi = {
  todayPlan: () =>
    api
      .get<DashboardTodayPlanResponse>("/api/sessions/today-plan")
      .then((r) => r.data),

  startOrContinueToday: () =>
    api
      .post<DashboardStartResponse>("/api/sessions/today/start-or-continue")
      .then((r) => r.data),

  start: (payload: SessionStartRequest) =>
    api
      .post<SessionStartResponse>("/api/sessions/start", payload)
      .then((r) => r.data),

  startToday: () =>
    api
      .post<SessionStartResponse>("/api/sessions/start-today")
      .then((r) => r.data),

  nextActivity: (sessionId: string) =>
    api
      .get<NextActivityResponse>(`/api/sessions/${sessionId}/next-activity`)
      .then((r) => r.data),

  submit: (sessionId: string, sequence: number, payload: SubmitActivityRequest) =>
    api
      .post<SubmitActivityResponse>(
        `/api/sessions/${sessionId}/activities/${sequence}/submit`,
        payload,
      )
      .then((r) => r.data),

  complete: (sessionId: string) =>
    api
      .post<SessionScorecardRead>(`/api/sessions/${sessionId}/complete`)
      .then((r) => r.data),

  getScorecard: (sessionId: string) =>
    api
      .get<SessionScorecardRead>(`/api/sessions/${sessionId}/scorecard`)
      .then((r) => r.data),

  // Coach's Note reactions now go through feedbackApi.react()
  // (feedback_type=COACH_NOTE, feedback_id=scorecard_id).

  advanceDay: () =>
    api
      .post<AdvanceDayResponse>("/api/sessions/advance-day")
      .then((r) => r.data),

  scorePronunciation: (audio: Blob, referenceText: string, language: string = "en-US") => {
    const formData = new FormData();
    formData.append("audio", audio, "recording.wav");
    formData.append("reference_text", referenceText);
    formData.append("language", language);
    return api
      .post<PronunciationResult>("/api/sessions/pronunciation-score", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
};

// ── Learning (chat) session endpoints (mounted under /api/learning) ──

export const learningSessionApi = {
  getState: (sessionId: string) =>
    api
      .get<LearningSessionState>(`/api/learning/sessions/${sessionId}/state`)
      .then((r) => r.data),

  resetActivity: (sessionId: string, sequence: number) =>
    api
      .post<LearningRestartResponse>(
        `/api/learning/sessions/${sessionId}/activities/${sequence}/reset`,
      )
      .then((r) => r.data),

  // Re-run feedback for one already-graded activity in place. The score and the
  // graded response are untouched; returns a fresh feedback card to swap in.
  regenerateFeedback: (sessionId: string, sequence: number) =>
    api
      .post<RegenerateFeedbackResponse>(
        `/api/learning/sessions/${sessionId}/activities/${sequence}/regenerate-feedback`,
      )
      .then((r) => r.data),
};
