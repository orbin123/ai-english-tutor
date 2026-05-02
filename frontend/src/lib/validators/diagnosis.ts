import { z } from "zod";

// Mirror backend enums (kept in sync by hand — short list)
export const SELF_LEVELS = ["beginner", "intermediate", "advanced"] as const;
export const EXPOSURES = ["none", "low", "medium", "high"] as const;
export const GOALS = ["casual", "professional", "academic"] as const;

// Step 1: self-assessment
export const selfAssessmentSchema = z.object({
  self_assessed_level: z.enum(SELF_LEVELS),
  goal: z.enum(GOALS),
  daily_time_minutes: z.coerce
    .number()
    .int()
    .min(5, "Minimum 5 minutes")
    .max(240, "Maximum 240 minutes"),
  content_exposure: z.enum(EXPOSURES),
  interests: z.array(z.string().min(1)).max(3),
});

// Step 2: fill-blank
export const fillBlankSchema = z.object({
  answers: z
    .array(z.string().min(1, "Please answer this blank"))
    .length(5, "All 5 blanks are required"),
});

// Step 3: writing
export const writingSchema = z.object({
  response_text: z
    .string()
    .min(10, "Write at least 10 characters")
    .max(2000, "Maximum 2000 characters"),
});

// Step 4: read-aloud — user must record audio and receive a transcript back
// from POST /diagnosis/transcribe before submitting the main form.
// audioBlob holds the raw recording in memory only (not submitted in JSON).
// transcript + duration_seconds come from the transcribe response and ARE
// included in the final JSON submit.
export const readAloudSchema = z.object({
  // The recorded audio blob — stored in form state only, never sent as JSON.
  // We use z.instanceof(Blob) so the form validates that a recording exists.
  audioBlob: z
    .instanceof(typeof window !== "undefined" ? Blob : Object as unknown as typeof Blob)
    .refine((b) => (b as Blob).size > 0, {
      message: "Please record your voice reading the passage",
    }),
  // From Whisper — populated after transcribe call succeeds
  transcript: z.string().min(1, "Transcription is missing — please record again"),
  duration_seconds: z.number().positive("Duration must be greater than 0"),
});

// Combined schema — used for the whole multi-step form
export const diagnosisSchema = z.object({
  self_assessment: selfAssessmentSchema,
  fill_blank: fillBlankSchema,
  writing: writingSchema,
  read_aloud: readAloudSchema,
});

export type DiagnosisFormInput = z.input<typeof diagnosisSchema>;
export type DiagnosisInput = z.output<typeof diagnosisSchema>;
