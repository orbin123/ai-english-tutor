import { api } from "./api";
import type { DiagnosisInput } from "./validators/diagnosis";

// Versioned IDs the backend expects
const QUESTION_SET_ID = "diag_fillblank_v1";
const WRITING_PROMPT_ID = "diag_writing_v1";
const READ_ALOUD_PASSAGE_ID = "diag_passage_v1";

// ── Types ──────────────────────────────────────────────────────────────────

export interface TranscribeResult {
  transcript: string;
  duration_seconds: number;
}

export interface WeakSkillExplanation {
  skill_name: string;
  what_it_means: string;
  why_it_matters: string;
  what_to_expect: string;
}

export interface DiagnosisFeedback {
  estimated_level_label: string;
  summary: string;
  weak_skill_explanations: WeakSkillExplanation[];
  motivation: string;
  first_week_focus: string;
}

export interface DiagnosisResult {
  skill_scores: Record<string, number>;
  weakest_skills: string[];
  feedback: DiagnosisFeedback;
  next_step: string;
}

// ── API calls ──────────────────────────────────────────────────────────────

export const diagnosisApi = {
  /**
   * Upload an audio blob to Whisper transcription.
   * Called when the user finishes recording in StepReadAloud.
   * Returns the transcript text + duration so they can be included in submit().
   */
  transcribe: (audioBlob: Blob): Promise<TranscribeResult> => {
    const formData = new FormData();
    // Give the file a name with the correct extension so the backend
    // can detect the format. Browsers record in webm by default.
    const mimeType = audioBlob.type || "audio/webm";
    const ext = mimeType.includes("mp4") ? "mp4" : "webm";
    formData.append("audio", audioBlob, `recording.${ext}`);

    return api
      .post<TranscribeResult>("/diagnosis/transcribe", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  /**
   * Submit the full diagnosis form.
   * read_aloud sends transcript + duration_seconds (from transcribe()),
   * NOT the audio blob — keeps this endpoint clean JSON.
   */
  submit: (data: DiagnosisInput): Promise<DiagnosisResult> => {
    const payload = {
      self_assessment: data.self_assessment,
      fill_blank: {
        question_set_id: QUESTION_SET_ID,
        answers: data.fill_blank.answers,
      },
      writing: {
        prompt_id: WRITING_PROMPT_ID,
        response_text: data.writing.response_text,
      },
      read_aloud: {
        passage_id: READ_ALOUD_PASSAGE_ID,
        transcript: data.read_aloud.transcript,
        duration_seconds: data.read_aloud.duration_seconds,
      },
    };
    return api
      .post<DiagnosisResult>("/diagnosis/submit", payload)
      .then((r) => r.data);
  },
};
