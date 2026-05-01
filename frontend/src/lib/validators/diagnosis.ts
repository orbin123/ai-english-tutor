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
  // Up to 3 interests; allow 0 (optional)
  interests: z.array(z.string().min(1)).max(3),
});

// Step 2: fill-blank — must be exactly 5 non-empty answers
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

// Step 4: read-aloud (stubbed — no real audio yet)
export const readAloudSchema = z.object({
  acknowledged: z.literal(true, {
    message: "Please confirm you read the passage aloud",
  }),
});

// Combined schema — used for the whole multi-step form
export const diagnosisSchema = z.object({
  self_assessment: selfAssessmentSchema,
  fill_blank: fillBlankSchema,
  writing: writingSchema,
  read_aloud: readAloudSchema,
});

export type DiagnosisInput = z.infer<typeof diagnosisSchema>;
