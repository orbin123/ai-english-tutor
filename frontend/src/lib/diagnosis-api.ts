import { api } from "./api";
import type { DiagnosisInput } from "./validators/diagnosis";

// Hardcoded IDs the backend expects (versioned so we can change later)
const QUESTION_SET_ID = "diag_fillblank_v1";
const WRITING_PROMPT_ID = "diag_writing_v1";
const READ_ALOUD_PASSAGE_ID = "diag_passage_v1";

// Stubbed read-aloud — we don't record audio yet
const STUB_AUDIO_URL = "stub://no-audio";
const STUB_DURATION_SECONDS = 30;

export interface DiagnosisResult {
  skill_scores: Record<string, number>; // { grammar: 3.0, vocabulary: 2.7, ... }
  weakest_skills: string[]; // ["grammar", "vocabulary"]
  next_step: string;
}

export const diagnosisApi = {
  submit: (data: DiagnosisInput) => {
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
        audio_url: STUB_AUDIO_URL,
        duration_seconds: STUB_DURATION_SECONDS,
      },
    };
    return api
      .post<DiagnosisResult>("/diagnosis/submit", payload)
      .then((r) => r.data);
  },
};
