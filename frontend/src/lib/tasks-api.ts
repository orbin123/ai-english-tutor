import { api } from "./api";

// ────────────────────────────────────────────────────────────────────
// Types — mirror the backend Pydantic / JSON shapes
// ────────────────────────────────────────────────────────────────────

// ---- Activity 1: Fill in the blanks ----
export interface FillInBlanksActivity {
  activity_id: string;
  activity_type: "fill_in_the_blanks";
  instruction: string;
  questions: Record<string, string>; // { Q1: "She ___ (be) a teacher.", ... }
  // Note: backend hides 'answers' from the user — we don't expect it here.
  answers?: Record<string, string>;
}

// ---- Activity 2: Paraphrasing ----
// User reads `questions[Qx]` (an original sentence) and types a rewrite.
// `reference_answers` and `min_words` are sent to the frontend so we can
// show hints + warn about too-short answers BEFORE the user submits.
export interface ParaphrasingActivity {
  activity_id: string;
  activity_type: "paraphrasing";
  instruction: string;
  questions: Record<string, string>;
  min_words?: number;
  reference_answers?: Record<string, string>;
}

// ---- Activity 3: Sentence engineering ----
// User reads scrambled `words` and clicks them in the correct order.
// The frontend assembles a string and submits it the same way as FIB.
export interface SentenceEngineeringQuestion {
  words: string[];
}
export interface SentenceEngineeringActivity {
  activity_id: string;
  activity_type: "sentence_engineering";
  instruction: string;
  questions: Record<string, SentenceEngineeringQuestion>;
  // Note: backend hides 'answers' from the user.
  answers?: Record<string, string>;
}

// Discriminated union — TypeScript will narrow correctly on activity_type
export type TaskActivity =
  | FillInBlanksActivity
  | ParaphrasingActivity
  | SentenceEngineeringActivity;

// ---- Task content envelope ----
// All current tasks share this shape; only the activities array differs.
export interface TaskContent {
  instruction: string;
  source: { type: "passage"; text: string };
  activities: TaskActivity[];
}

// What `/tasks/next` returns
export interface UserTask {
  id: number;
  user_id: number;
  task_id: number;
  enrollment_id: number | null;
  status: "pending" | "in_progress" | "completed" | "skipped";
  completed_at: string | null;
  created_at: string;
  task: {
    id: number;
    title: string;
    task_type: "reading" | "writing" | "speaking" | "listening";
    difficulty: number;
    status: "draft" | "active" | "archived";
    content: TaskContent;
  };
}

// What `/responses/submit` returns (the full graded bundle)
export interface SkillScore {
  skill_id: number;
  skill_name: string;
  score: number;
}

export interface ResponseGraded {
  response: {
    id: number;
    user_task_id: number;
    content: Record<string, string>;
    raw_text: string | null;
    created_at: string;
  };
  evaluation: {
    id: number;
    overall_score: number;
    percentage: number;
    report: Record<string, unknown>;
  };
  feedback: {
    id: number;
    body: Record<string, unknown>;
  };
  skill_scores: SkillScore[];
}

// ────────────────────────────────────────────────────────────────────
// API calls
// ────────────────────────────────────────────────────────────────────

export const tasksApi = {
  // Backend endpoint is POST /tasks/next (idempotent — same task on retry)
  getNext: () => api.post<UserTask>("/tasks/next").then((r) => r.data),

  submitResponse: (payload: {
    user_task_id: number;
    content: Record<string, string>;
    raw_text?: string;
  }) =>
    api
      .post<ResponseGraded>("/responses/submit", payload)
      .then((r) => r.data),
};
