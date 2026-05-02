"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import {
  diagnosisSchema,
  type DiagnosisFormInput,
  type DiagnosisInput,
} from "@/lib/validators/diagnosis";
import { useDiagnosis } from "@/hooks/useDiagnosis";
import { useAuthStore } from "@/store/authStore";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { authApi } from "@/lib/auth-api";
import { diagnosisApi } from "@/lib/diagnosis-api";
import { getApiErrorMessage } from "@/lib/errors";

/* ──────────────────────────────────────────────────────────────────────────
 *  LingosAI — Diagnosis page
 * ────────────────────────────────────────────────────────────────────────── */

const STEP_LABELS = [
  "About you",
  "Fill the blanks",
  "Short writing",
  "Read aloud",
] as const;

const PROFICIENCY_OPTIONS = [
  { label: "Beginner", value: "beginner" },
  { label: "Intermediate", value: "intermediate" },
  { label: "Advanced", value: "advanced" },
];
const GOAL_OPTIONS = [
  { label: "Casual", value: "casual" },
  { label: "Professional", value: "professional" },
  { label: "Academic", value: "academic" },
];
const EXPOSURE_OPTIONS = [
  { label: "Never", value: "none" },
  { label: "Sometimes", value: "low" },
  { label: "Often", value: "medium" },
  { label: "Daily", value: "high" },
];
const INTERESTS = ["tech", "business", "movies", "sports", "travel", "music"] as const;

const FILL_QUESTIONS = [
  { sentence: "She ___ to school every morning.", hint: '"go"' },
  { sentence: "I ___ rice for lunch yesterday.", hint: '"eat" in past tense' },
  { sentence: "It always ___ a lot in July.", hint: '"rain"' },
  { sentence: "They ___ in Mumbai for ten years.", hint: '"live" in past tense' },
  { sentence: "The novel ___ by a famous author.", hint: '"write" — passive past' },
] as const;

const PASSAGE =
  "Every morning I wake up early and walk in the park. The fresh air helps me think clearly. I greet a few neighbours, finish a short jog, and return home feeling ready for the day.";

const FIELDS_PER_STEP = [
  ["self_assessment"],
  ["fill_blank"],
  ["writing"],
  ["read_aloud"],
] as const;

const DEFAULT_VALUES: DiagnosisFormInput = {
  self_assessment: {
    self_assessed_level: "beginner",
    goal: "professional",
    daily_time_minutes: 15,
    content_exposure: "low",
    interests: [],
  },
  fill_blank: { answers: ["", "", "", "", ""] },
  writing: { response_text: "" },
  read_aloud: {
    audioBlob: undefined as unknown as Blob,
    transcript: "",
    duration_seconds: 0,
  },
};

/* ── Inline icons ──────────────────────────────────────────────────────── */
function ArrowRightIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function ArrowLeftIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M13 8H3M7 4l-4 4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function CheckIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
      <path d="M3 7.5L6 10.5L11 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function SpinIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.3" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
function MicIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
      <rect x="7" y="2" width="6" height="10" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 10a6 6 0 0 0 12 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="10" y1="16" x2="10" y2="19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
function StopIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="3" y="3" width="12" height="12" rx="2" fill="currentColor" />
    </svg>
  );
}
function RefreshIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path d="M13 7A6 6 0 1 1 7 1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M7 1l2.5 2.5L7 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ── Stepper ──────────────────────────────────────────────────────────── */
function Stepper({ current }: { current: number }) {
  return (
    <ol className="mb-8 flex items-center gap-1 sm:gap-2" aria-label="Progress">
      {STEP_LABELS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        const upcoming = i > current;
        return (
          <li key={label} className="flex flex-1 items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-2 sm:gap-3">
              <div
                className={[
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[13px] font-bold transition-colors",
                  done && "bg-blue-600 text-white",
                  active && "bg-[#0a0f1f] text-white ring-4 ring-blue-100",
                  upcoming && "border border-slate-300 bg-white text-slate-400",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={active ? "step" : undefined}
              >
                {done ? <CheckIcon /> : i + 1}
              </div>
              <span
                className={[
                  "hidden text-[13px] sm:inline",
                  active ? "font-semibold text-[#0a1f44]" : done ? "font-medium text-[#0a1f44]" : "text-slate-400",
                ].join(" ")}
              >
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div className="mx-1 h-px flex-1 overflow-hidden bg-slate-200">
                <div
                  className="h-full bg-blue-600 transition-all duration-500"
                  style={{ width: i < current ? "100%" : "0%" }}
                />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white px-3 py-1 text-[12.5px] font-semibold text-blue-800 shadow-sm">
      <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
      {children}
    </div>
  );
}

interface SegmentedProps {
  options: ReadonlyArray<{ label: string; value: string }>;
  value: string | undefined;
  onChange: (v: string) => void;
  ariaLabel?: string;
}
function Segmented({ options, value, onChange, ariaLabel }: SegmentedProps) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const selected = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(opt.value)}
            className={[
              "rounded-full px-4 py-2 text-[13.5px] font-semibold transition-all",
              selected
                ? "bg-[#0a0f1f] text-white shadow-[0_4px_14px_rgba(10,15,31,0.18)]"
                : "border border-slate-200 bg-white text-[#0a1f44] hover:border-slate-300",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function FieldRow({
  label, helper, error, children,
}: {
  label: string; helper?: string; error?: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white px-6 py-4 shadow-[0_2px_10px_rgba(15,23,42,0.04)]">
      <div className="mb-2">
        <div className="text-[14.5px] font-semibold text-[#0a1f44]">{label}</div>
        {helper && <div className="mt-0.5 text-[12.5px] text-slate-500">{helper}</div>}
      </div>
      {children}
      {error && <p className="mt-2 text-[12.5px] font-medium text-red-600">{error}</p>}
    </div>
  );
}

/* ── Step 1 ────────────────────────────────────────────────────────────── */
function StepAboutYou({ form }: { form: ReturnType<typeof useForm<DiagnosisFormInput, unknown, DiagnosisInput>> }) {
  const { control, register, watch, setValue, formState: { errors } } = form;
  const studyMinutes = (watch("self_assessment.daily_time_minutes") as number) ?? 15;
  const interests = (watch("self_assessment.interests") as string[]) ?? [];

  const toggleInterest = (key: string) => {
    const set = new Set(interests);
    if (set.has(key)) set.delete(key);
    else if (set.size < 3) set.add(key);
    setValue("self_assessment.interests", Array.from(set) as string[], { shouldValidate: true });
  };

  return (
    <div className="space-y-3">
      <Eyebrow>Quick self-assessment</Eyebrow>
      <h2 className="text-2xl font-extrabold tracking-tight text-[#0a1f44] sm:text-[28px]">Tell us about your English goals</h2>
      <p className="text-[15px] text-slate-600">This helps us pick the right starting point for you.</p>
      <div className="mt-5 space-y-3">
        <Controller control={control} name="self_assessment.self_assessed_level" render={({ field }) => (
          <FieldRow label="How would you rate your English?" error={errors.self_assessment?.self_assessed_level?.message}>
            <Segmented options={PROFICIENCY_OPTIONS} value={field.value} onChange={field.onChange} ariaLabel="Proficiency level" />
          </FieldRow>
        )} />
        <Controller control={control} name="self_assessment.goal" render={({ field }) => (
          <FieldRow label="What's your main goal?" error={errors.self_assessment?.goal?.message}>
            <Segmented options={GOAL_OPTIONS} value={field.value} onChange={field.onChange} ariaLabel="Main goal" />
          </FieldRow>
        )} />
        <FieldRow label="Daily study time" helper="How many minutes a day can you commit?" error={errors.self_assessment?.daily_time_minutes?.message}>
          <div className="flex items-center gap-3">
            <div className="flex items-center overflow-hidden rounded-full border border-slate-200 bg-white">
              <button type="button" aria-label="Decrease minutes" onClick={() => setValue("self_assessment.daily_time_minutes", Math.max(5, (studyMinutes ?? 15) - 5), { shouldValidate: true })} className="px-4 py-2 text-lg text-[#0a1f44] hover:bg-slate-50">−</button>
              <input type="number" min={5} max={120} {...register("self_assessment.daily_time_minutes", { valueAsNumber: true })} className="w-20 border-x border-slate-200 bg-white py-2 text-center text-[14.5px] font-semibold text-[#0a1f44] outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
              <button type="button" aria-label="Increase minutes" onClick={() => setValue("self_assessment.daily_time_minutes", Math.min(120, (studyMinutes ?? 15) + 5), { shouldValidate: true })} className="px-4 py-2 text-lg text-[#0a1f44] hover:bg-slate-50">+</button>
            </div>
            <span className="text-[13.5px] font-medium text-slate-500">minutes</span>
          </div>
          <input type="range" min={5} max={120} step={5} value={studyMinutes ?? 15} onChange={(e) => setValue("self_assessment.daily_time_minutes", Number(e.target.value), { shouldValidate: true })} className="mt-4 w-full accent-blue-600" aria-label="Daily study time slider" />
          <div className="mt-1 flex justify-between text-[11px] text-slate-400"><span>5 min</span><span>120 min</span></div>
        </FieldRow>
        <Controller control={control} name="self_assessment.content_exposure" render={({ field }) => (
          <FieldRow label="English content exposure" helper="Movies, podcasts, books, social media, etc." error={errors.self_assessment?.content_exposure?.message}>
            <Segmented options={EXPOSURE_OPTIONS} value={field.value} onChange={field.onChange} ariaLabel="Content exposure" />
          </FieldRow>
        )} />
        <FieldRow label="Pick up to 3 interests" helper="Optional — helps us tailor your tasks." error={errors.self_assessment?.interests?.message}>
          <div className="flex flex-wrap gap-2">
            {INTERESTS.map((tag) => {
              const selected = interests.includes(tag);
              const limitReached = !selected && interests.length >= 3;
              return (
                <button key={tag} type="button" onClick={() => toggleInterest(tag)} disabled={limitReached}
                  className={["rounded-full px-3.5 py-1.5 text-[13px] font-semibold capitalize transition-all", selected ? "bg-blue-600 text-white shadow-[0_3px_10px_rgba(37,99,235,0.25)]" : "border border-slate-200 bg-white text-[#0a1f44] hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"].join(" ")}
                  aria-pressed={selected}>{tag}</button>
              );
            })}
          </div>
          <p className="mt-2 text-[12px] text-slate-400">{interests.length}/3 selected</p>
        </FieldRow>
      </div>
    </div>
  );
}

/* ── Step 2 ────────────────────────────────────────────────────────────── */
function StepFillBlanks({ form }: { form: ReturnType<typeof useForm<DiagnosisFormInput, unknown, DiagnosisInput>> }) {
  const { register, formState: { errors } } = form;
  const blankRegex = /_+/;
  return (
    <div className="space-y-3">
      <Eyebrow>Quick grammar check</Eyebrow>
      <h2 className="text-2xl font-extrabold tracking-tight text-[#0a1f44] sm:text-[28px]">Fill in the blanks</h2>
      <p className="text-[15px] text-slate-600">Type one word per blank. The hint shows the base verb.</p>
      <ol className="mt-5 space-y-3">
        {FILL_QUESTIONS.map((q, i) => {
          const parts = q.sentence.split(blankRegex);
          const fieldName = `fill_blank.answers.${i}` as const;
          const fieldError = errors.fill_blank?.answers?.[i]?.message;
          return (
            <li key={i} className="rounded-2xl border border-slate-100 bg-white p-5 shadow-[0_2px_10px_rgba(15,23,42,0.04)]">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-[12.5px] font-bold text-white">{i + 1}</div>
                <div className="flex-1">
                  <p className="text-[15px] leading-relaxed text-[#0a1f44]">{parts[0]}<span className="mx-1 inline-block min-w-[60px] border-b-2 border-dashed border-blue-300 align-baseline" />{parts[1]}</p>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                    <input {...register(`fill_blank.answers.${i}` as `fill_blank.answers.${number}`)} type="text" placeholder="Your answer" autoComplete="off" aria-label={`Answer ${i + 1}`}
                      className={["w-full rounded-lg border bg-white px-3.5 py-2 text-[14.5px] text-[#0a1f44] outline-none transition-colors placeholder:text-slate-400 focus:ring-2 focus:ring-blue-200/60", fieldError ? "border-red-400 focus:border-red-500" : "border-slate-200 focus:border-blue-500", "sm:max-w-xs"].join(" ")} />
                    <span className="text-[12.5px] italic text-slate-500">(hint: {q.hint})</span>
                  </div>
                  {fieldError && <p id={`${fieldName}-err`} className="mt-2 text-[12.5px] font-medium text-red-600">{fieldError}</p>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ── Step 3 ────────────────────────────────────────────────────────────── */
function StepWriting({ form }: { form: ReturnType<typeof useForm<DiagnosisFormInput, unknown, DiagnosisInput>> }) {
  const { register, watch, formState: { errors } } = form;
  const text = watch("writing.response_text") ?? "";
  const wordCount = text.trim().length === 0 ? 0 : text.trim().split(/\s+/).length;
  return (
    <div className="space-y-3">
      <Eyebrow>Free writing</Eyebrow>
      <h2 className="text-2xl font-extrabold tracking-tight text-[#0a1f44] sm:text-[28px]">Describe your typical day</h2>
      <p className="text-[15px] text-slate-600">Write 3–5 sentences. Don&apos;t worry about perfection.</p>
      <div className="mt-5">
        <textarea {...register("writing.response_text")} rows={6} placeholder="I usually wake up at..." aria-describedby="writing-counter"
          className={["w-full rounded-2xl border bg-white px-4 py-3 text-[15px] leading-relaxed text-[#0a1f44] outline-none transition-colors placeholder:text-slate-400 focus:ring-2 focus:ring-blue-200/60", errors.writing?.response_text ? "border-red-400 focus:border-red-500" : "border-slate-200 focus:border-blue-500", "shadow-[0_2px_10px_rgba(15,23,42,0.04)]"].join(" ")} />
        <div className="mt-2 flex items-center justify-between">
          <p className="text-[12.5px] text-slate-500">Tip: include morning, afternoon, and evening.</p>
          <p id="writing-counter" className={["text-[12.5px] font-semibold tabular-nums", wordCount >= 30 ? "text-green-600" : "text-slate-500"].join(" ")} aria-live="polite">{wordCount} / 60 words</p>
        </div>
        {errors.writing?.response_text && <p className="mt-2 text-[12.5px] font-medium text-red-600">{errors.writing.response_text.message}</p>}
      </div>
    </div>
  );
}

/* ── Step 4 — Read Aloud with real microphone recording ────────────────── */
type RecordState = "idle" | "recording" | "transcribing" | "done" | "error";

function StepReadAloud({ form }: { form: ReturnType<typeof useForm<DiagnosisFormInput, unknown, DiagnosisInput>> }) {
  const { setValue, watch, formState: { errors, submitCount } } = form;

  const [recordState, setRecordState] = useState<RecordState>("idle");
  const [elapsed, setElapsed] = useState(0);          // seconds while recording
  const [transcribeError, setTranscribeError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);  // for playback

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  // Current form values for transcript (to show confirmation)
  const transcript = watch("read_aloud.transcript") as string;
  const audioBlob = watch("read_aloud.audioBlob");

  // Clean up object URLs on unmount
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [audioUrl]);

  const startRecording = async () => {
    setTranscribeError(null);
    setElapsed(0);
    chunksRef.current = [];

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setTranscribeError("Microphone access was denied. Please allow microphone access and try again.");
      return;
    }

    // Pick the best supported MIME type
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "audio/mp4";

    const recorder = new MediaRecorder(stream, { mimeType });
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      // Stop all mic tracks
      stream.getTracks().forEach((t) => t.stop());

      const blob = new Blob(chunksRef.current, { type: mimeType });
      const duration = (Date.now() - startTimeRef.current) / 1000;

      // Create a playback URL
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(blob));

      // Store blob in form (for validation)
      setValue("read_aloud.audioBlob", blob, { shouldValidate: false });
      setValue("read_aloud.duration_seconds", duration, { shouldValidate: false });

      // Send to Whisper
      setRecordState("transcribing");
      try {
        const result = await diagnosisApi.transcribe(blob);
        setValue("read_aloud.transcript", result.transcript, { shouldValidate: true });
        setValue("read_aloud.duration_seconds", result.duration_seconds, { shouldValidate: true });
        setValue("read_aloud.audioBlob", blob, { shouldValidate: true });
        setRecordState("done");
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Transcription failed. Please try again.";
        setTranscribeError(msg);
        setRecordState("error");
      }
    };

    startTimeRef.current = Date.now();
    recorder.start(250); // collect data every 250ms
    setRecordState("recording");

    // Live timer
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 1000);
  };

  const stopRecording = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    mediaRecorderRef.current?.stop();
    setRecordState("transcribing"); // will be updated in onstop
  };

  const resetRecording = () => {
    setRecordState("idle");
    setElapsed(0);
    setTranscribeError(null);
    if (audioUrl) { URL.revokeObjectURL(audioUrl); setAudioUrl(null); }
    setValue("read_aloud.audioBlob", undefined as unknown as Blob, { shouldValidate: false });
    setValue("read_aloud.transcript", "", { shouldValidate: false });
    setValue("read_aloud.duration_seconds", 0, { shouldValidate: false });
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  const blobError = errors.read_aloud?.audioBlob?.message as string | undefined;
  const transcriptError = errors.read_aloud?.transcript?.message as string | undefined;
  const hasRecorded = !!audioBlob;
  const hasInteracted = recordState !== "idle";
  const displayError = transcribeError ?? (
    hasInteracted && (submitCount > 0 || hasRecorded)
      ? (transcriptError ?? blobError)
      : undefined
  );

  return (
    <div className="space-y-3">
      <Eyebrow>Pronunciation</Eyebrow>
      <h2 className="text-2xl font-extrabold tracking-tight text-[#0a1f44] sm:text-[28px]">
        Read this passage out loud
      </h2>
      <p className="text-[15px] text-slate-600">
        Press record, read the passage clearly, then press stop. We&apos;ll analyse your speech.
      </p>

      {/* Passage */}
      <blockquote className="mt-5 rounded-2xl border-l-4 border-blue-600 bg-blue-50/40 px-6 py-5 shadow-[0_2px_10px_rgba(15,23,42,0.04)]">
        <p className="text-[17px] italic leading-relaxed text-[#0a1f44]">
          &ldquo;{PASSAGE}&rdquo;
        </p>
      </blockquote>

      {/* Recorder UI */}
      <div className="mt-4 rounded-2xl border border-slate-100 bg-white p-5 shadow-[0_2px_10px_rgba(15,23,42,0.04)]">

        {/* idle */}
        {recordState === "idle" && (
          <div className="flex flex-col items-center gap-3 py-2">
            <p className="text-[13.5px] text-slate-500">Press record when you are ready.</p>
            <button
              type="button"
              onClick={startRecording}
              className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-6 py-3 text-[14.5px] font-bold text-white shadow-[0_4px_14px_rgba(37,99,235,0.3)] transition-all hover:bg-blue-700 active:scale-[0.98]"
            >
              <MicIcon /> Start recording
            </button>
          </div>
        )}

        {/* recording */}
        {recordState === "recording" && (
          <div className="flex flex-col items-center gap-3 py-2">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
              <span className="text-[14px] font-semibold text-red-600">Recording — {formatTime(elapsed)}</span>
            </div>
            <p className="text-[13px] text-slate-500">Read the passage above, then press stop.</p>
            <button
              type="button"
              onClick={stopRecording}
              className="inline-flex items-center gap-2 rounded-full bg-red-600 px-6 py-3 text-[14.5px] font-bold text-white shadow-[0_4px_14px_rgba(220,38,38,0.3)] transition-all hover:bg-red-700 active:scale-[0.98]"
            >
              <StopIcon /> Stop recording
            </button>
          </div>
        )}

        {/* transcribing */}
        {recordState === "transcribing" && (
          <div className="flex flex-col items-center gap-3 py-4">
            <SpinIcon className="h-6 w-6 text-blue-600" />
            <p className="text-[13.5px] font-medium text-slate-600">Analysing your speech…</p>
          </div>
        )}

        {/* done */}
        {recordState === "done" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-[13.5px] font-semibold text-emerald-700">
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100">
                <CheckIcon className="text-emerald-600" />
              </div>
              Recording complete
            </div>
            {/* Playback */}
            {audioUrl && (
              <audio controls src={audioUrl} className="w-full rounded-lg" aria-label="Your recording" />
            )}
            {/* Transcript preview */}
            {transcript && (
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-slate-400">What we heard</p>
                <p className="text-[13.5px] leading-relaxed text-[#0a1f44]">{transcript}</p>
              </div>
            )}
            <button
              type="button"
              onClick={resetRecording}
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-slate-500 hover:text-[#0a1f44]"
            >
              <RefreshIcon /> Record again
            </button>
          </div>
        )}

        {/* error */}
        {recordState === "error" && (
          <div className="space-y-3">
            <p className="text-[13.5px] font-medium text-red-600">{transcribeError}</p>
            <button
              type="button"
              onClick={resetRecording}
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-blue-600 hover:underline"
            >
              <RefreshIcon /> Try again
            </button>
          </div>
        )}
      </div>

      {displayError && recordState !== "error" && (
        <p className="text-[12.5px] font-medium text-red-600">{displayError}</p>
      )}
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────── */
export default function DiagnosisPage() {
  const router = useRouter();
  const { isReady } = useRequireAuth();
  const [currentStep, setCurrentStep] = useState(0);
  const [serverError, setServerError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: authApi.me,
    enabled: isReady,
  });
  useEffect(() => {
    if (me?.diagnosis_completed) router.replace("/dashboard");
  }, [me, router]);

  const form = useForm<DiagnosisFormInput, unknown, DiagnosisInput>({
    resolver: zodResolver(diagnosisSchema),
    defaultValues: DEFAULT_VALUES,
    mode: "onTouched",
  });

  const { mutate, isPending, error } = useDiagnosis();

  useEffect(() => {
    if (error) setServerError(getApiErrorMessage(error));
  }, [error]);

  useEffect(() => {
    const node = cardRef.current;
    if (!node) return;
    const first = node.querySelector<HTMLElement>(
      'input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), button[role="radio"]',
    );
    first?.focus({ preventScroll: true });
  }, [currentStep]);

  const goNext = async () => {
    setServerError(null);
    const ok = await form.trigger(FIELDS_PER_STEP[currentStep] as any);
    if (!ok) return;
    if (currentStep < STEP_LABELS.length - 1) setCurrentStep((s) => s + 1);
  };

  const goBack = () => {
    setServerError(null);
    if (currentStep > 0) setCurrentStep((s) => s - 1);
  };

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    mutate(values as DiagnosisInput);
  });

  const isLastStep = currentStep === STEP_LABELS.length - 1;
  if (!isReady) return null;

  return (
    <main
      className="relative min-h-screen w-full bg-gradient-to-b from-[#dbeafe] to-[#eff6ff]"
      style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
    >
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" />
      <div aria-hidden className="pointer-events-none absolute inset-0" style={{ backgroundImage: "radial-gradient(circle, rgba(37,99,235,0.10) 1px, transparent 1px)", backgroundSize: "22px 22px" }} />

      <header className="relative z-10 flex items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" className="group inline-flex items-center gap-2" aria-label="LingosAI home">
          <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-blue-600 transition-transform group-hover:scale-105">
            <span className="text-[17px] font-extrabold leading-none text-white">A</span>
          </div>
          <span className="text-[17px] font-bold tracking-tight text-[#0a1f44]">LingosAI</span>
        </Link>
      </header>

      <section className="relative z-10 mx-auto w-full max-w-[760px] px-4 pb-20 pt-2 sm:px-6">
        <div ref={cardRef} className="rounded-3xl border border-white/90 bg-white/90 px-5 py-8 shadow-[0_8px_32px_rgba(15,23,42,0.06)] backdrop-blur-xl sm:px-10 sm:py-10">
          <Stepper current={currentStep} />
          <form onSubmit={onSubmit} noValidate>
            <div key={currentStep} className="animate-[fadeIn_0.35s_ease]" style={{ animationFillMode: "both" }}>
              {currentStep === 0 && <StepAboutYou form={form} />}
              {currentStep === 1 && <StepFillBlanks form={form} />}
              {currentStep === 2 && <StepWriting form={form} />}
              {currentStep === 3 && <StepReadAloud form={form} />}
            </div>

            {serverError && (
              <div role="alert" className="mt-6 flex items-start gap-2.5 rounded-full bg-red-50 px-4 py-2.5 text-[13.5px] font-medium text-red-700">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mt-0.5 shrink-0" aria-hidden><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" /><path d="M8 5v3.5M8 11v.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
                <span>{serverError}</span>
              </div>
            )}

            <div className="mt-10 flex items-center justify-between gap-3 border-t border-slate-100 pt-6">
              <button type="button" onClick={goBack} disabled={currentStep === 0 || isPending}
                className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-5 py-2.5 text-[14px] font-semibold text-[#0a1f44] transition-all hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
                <ArrowLeftIcon /> Back
              </button>

              {isLastStep ? (
                <button type="submit" disabled={isPending}
                  className="inline-flex items-center gap-2 rounded-full bg-[#0a0f1f] px-6 py-3 text-[14.5px] font-bold text-white shadow-[0_4px_18px_rgba(10,15,31,0.25)] transition-all hover:scale-[1.02] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60">
                  {isPending ? <><SpinIcon className="text-white" /> Submitting…</> : <>Submit diagnosis <ArrowRightIcon /></>}
                </button>
              ) : (
                <button type="button" onClick={goNext}
                  className="inline-flex items-center gap-2 rounded-full bg-[#0a0f1f] px-6 py-3 text-[14.5px] font-bold text-white shadow-[0_4px_18px_rgba(10,15,31,0.25)] transition-all hover:scale-[1.02] active:scale-[0.99]">
                  Next <ArrowRightIcon />
                </button>
              )}
            </div>
          </form>
        </div>
        <p className="mt-5 text-center text-[12.5px] text-slate-500">Your answers are private and used only to personalize your coaching plan.</p>
      </section>

      <style jsx>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </main>
  );
}
