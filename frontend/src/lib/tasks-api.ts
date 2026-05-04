import { api } from "./api";

// ────────────────────────────────────────────────────────────────────
// Types — mirror the backend Pydantic / JSON shapes
// ────────────────────────────────────────────────────────────────────

// ═══════════════════════════════════════════════════════════════════
// SEEDED TASK TYPES (backward-compatible — old activity-based tasks)
// ═══════════════════════════════════════════════════════════════════

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

// ---- Task content envelope (seeded tasks) ----
// All seeded tasks share this shape; only the activities array differs.
export interface SeededTaskContent {
  instruction: string;
  source: { type: "passage"; text: string };
  activities: TaskActivity[];
}

// ═══════════════════════════════════════════════════════════════════
// GENERATED TASK TYPES (LLM-generated — from grammar_templates.py)
// ═══════════════════════════════════════════════════════════════════

// Shared grammar rule literal
export type GrammarRule =
  | "past_simple"
  | "past_continuous"
  | "present_simple"
  | "present_perfect"
  | "past_perfect"
  | "future_simple"
  | "subject_verb_agreement"
  | "preposition"
  | "article"
  | "conditional"
  | "passive_voice"
  | "active_voice"
  | "modal_verb"
  | "relative_clause"
  | "conjunction";

// Base fields every generated task has
interface GeneratedTaskBase {
  task_intro: string;
  estimated_time_minutes: number;
}

// ── Template 1: Fill-in-Blanks ──────────────────────────────────
export interface BlankItem {
  blank_id: string;
  sentence_with_blank: string;
  correct_answer: string;
  options: [string, string, string, string];
  grammar_rule: GrammarRule;
  explanation: string;
}

export interface FillInBlanksTaskContent extends GeneratedTaskBase {
  passage_title: string;
  passage: string;
  blanks: BlankItem[];
  total_blanks: number;
}

// ── Template 2: Error Spotting ──────────────────────────────────
export interface ErrorItem {
  sentence_id: string;
  sentence: string;
  has_error: boolean;
  error_type: GrammarRule | null;
  incorrect_phrase: string | null;
  correction: string | null;
  explanation: string | null;
}

export interface ErrorSpottingTaskContent extends GeneratedTaskBase {
  instructions: string;
  sentences: ErrorItem[];
  total_with_errors: number;
}

// ── Template 3: Sentence Transformation ─────────────────────────
export interface TransformItem {
  item_id: string;
  original_sentence: string;
  transformation_target:
    | "make_complex"
    | "make_compound"
    | "add_relative_clause"
    | "use_conditional"
    | "combine_sentences";
  expected_pattern: string;
  sample_correct_answer: string;
  grading_criteria: string[];
}

export interface SentenceTransformationTaskContent extends GeneratedTaskBase {
  instructions: string;
  items: TransformItem[];
}

// ── Template 4: Voice Conversion ────────────────────────────────
export interface VoiceConversionItem {
  item_id: string;
  original_sentence: string;
  direction: "active_to_passive" | "passive_to_active";
  correct_answer: string;
  common_mistake: string | null;
}

export interface VoiceConversionTaskContent extends GeneratedTaskBase {
  instructions: string;
  items: VoiceConversionItem[];
}

// ── Template 5: Error Correction ────────────────────────────────
export interface CorrectionItem {
  item_id: string;
  incorrect_sentence: string;
  correct_sentence: string;
  error_type: GrammarRule;
  explanation: string;
}

export interface ErrorCorrectionTaskContent extends GeneratedTaskBase {
  instructions: string;
  items: CorrectionItem[];
}

// Union of all generated task content shapes.
// Discrimination happens via task.task_type (outer object), not a field inside content.
export type GeneratedTaskContent =
  | FillInBlanksTaskContent
  | ErrorSpottingTaskContent
  | SentenceTransformationTaskContent
  | VoiceConversionTaskContent
  | ErrorCorrectionTaskContent;

// The known task_type strings for generated tasks
export type GeneratedTaskType =
  | "fill_in_blanks"
  | "error_spotting"
  | "sentence_transformation"
  | "voice_conversion"
  | "error_correction";

// The known task_type strings for old seeded tasks
export type SeededTaskType = "reading" | "writing" | "speaking" | "listening";

const GENERATED_TASK_TYPES: Set<string> = new Set([
  "fill_in_blanks",
  "error_spotting",
  "sentence_transformation",
  "voice_conversion",
  "error_correction",
]);

/** Check if a task_type string is a generated (LLM) task type */
export function isGeneratedTaskType(taskType: string): taskType is GeneratedTaskType {
  return GENERATED_TASK_TYPES.has(taskType);
}

// ═══════════════════════════════════════════════════════════════════
// USER TASK — what GET /tasks/next returns (now an array)
// ═══════════════════════════════════════════════════════════════════

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
    task_type: string;
    difficulty: number;
    status: "draft" | "active" | "archived";
    content: SeededTaskContent | GeneratedTaskContent;
  };
}

// ═══════════════════════════════════════════════════════════════════
// RESPONSE / GRADING TYPES
// ═══════════════════════════════════════════════════════════════════

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

// ════════════════════════════════════════════════════════════════════
// API calls
// ════════════════════════════════════════════════════════════════════

export const tasksApi = {
  // Backend endpoint is POST /tasks/next — returns the day bundle (array)
  getNext: () =>
    api.post<UserTask[]>("/tasks/next").then((r) => r.data),

  submitResponse: (payload: {
    user_task_id: number;
    content: Record<string, string>;
    raw_text?: string;
  }) =>
    api
      .post<ResponseGraded>("/responses/submit", payload)
      .then((r) => r.data),

  // Mark the entire day as complete after all tasks in the bundle are submitted
  completeDay: () =>
    api.post("/tasks/complete-day").then((r) => r.data),

  // Superuser-only: jump to a specific week/day to generate tasks for it
  superuserJump: (week: number, dayInWeek: number) =>
    api
      .post<UserTask[]>("/tasks/superuser-jump", {
        week,
        day_in_week: dayInWeek,
      })
      .then((r) => r.data),
};
