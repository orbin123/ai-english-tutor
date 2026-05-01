import { api } from "./api";

// ────────────────────────────────────────────────────────────────────
// Types — mirror the backend Pydantic schemas
// ────────────────────────────────────────────────────────────────────

// One fill-in-the-blanks activity inside a task
export interface FillInBlanksActivity {
  activity_id: string;
  activity_type: "fill_in_the_blanks";
  instruction: string;
  questions: Record<string, string>; // { Q1: "She ___ (be) a teacher.", ... }
  // Note: backend hides 'answers' from the user — we don't expect it here.
  answers?: Record<string, string>;
}

// The shape of `content` for a reading + fill-in-blanks task
export interface ReadingTaskContent {
  instruction: string;
  source: { type: "passage"; text: string };
  activities: FillInBlanksActivity[];
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
    content: ReadingTaskContent; // for now we only handle reading; widen later
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
