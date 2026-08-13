"use client";

import { useEffect, useRef, useState } from "react";
import { tasksApi } from "@/lib/tasks-api";
import { sessionsApi, type PronunciationResult } from "@/lib/sessions-api";
import { blobToWav } from "@/lib/audio-utils";
import { MAX_AUDIO_RECORDING_SECONDS } from "@/lib/audio-limits";
import { resolveMediaUrl } from "@/lib/api-config";
import type { SessionWidgetProps } from "./types";

interface SpeakRoleplayTurn {
  turn_id: string;
  speaker: "ai" | "user";
  ai_line?: string | null;
}

interface SpeakAndRecordPayload {
  topic_override?: string;
  topic?: string;
  task_intro?: string;
  instructions_override?: string;
  instructions?: string;
  sub_skill?: string;
  activity?: string;
  estimated_time_minutes?: number;
  grammar_rule_to_practice?: string;
  target_pattern?: string;
  target_tone?: string;
  source_audio_url?: string | null;
  source_audio_script?: string;
  reference_audio_url?: string | null;
  scenario_description?: string;
  preparation_seconds?: number;
  speaking_duration_seconds?: number;
  speaking_prompts?: string[];
  speaking_items?: string[];
  sample_responses?: string[];
  text_to_read_aloud?: string;
  primary_text?: string;
  passage?: string;
  retelling_prompt?: string;
  sample_response?: string | null;
  speaking_prompt?: string;
  sample_user_responses?: string[];
  turns?: SpeakRoleplayTurn[];
  target_words?: string[];
  key_points_expected?: string[];
  sample_talking_points?: string[];
}

const I = {
  rule: "Rule",
  clock: "Clock",
  mic: "Mic",
  stop: "Stop",
  replay: "Again",
  send: "Send",
};

function TaskHeader({
  topic,
  intro,
  sub_skill,
  activity,
  time,
}: {
  topic: string;
  intro: { title: string; body: string };
  sub_skill: string;
  activity: string;
  time: number;
}) {
  return (
    <div className="tw-task-header">
      <div className="tw-task-topic">{topic}</div>
      <div className="tw-task-title">{intro.title}</div>
      <div className="tw-task-intro">{intro.body}</div>
      <div className="tw-task-pill-row">
        {sub_skill && <span className="tw-task-pill"><span className="tw-dot" />{sub_skill}</span>}
        {activity && <span className="tw-task-pill activity"><span className="tw-dot" />{activity}</span>}
        {time > 0 && <span className="tw-task-pill time"><span className="tw-dot" />{time} min</span>}
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function resolveAudioUrl(url?: string | null): string | null {
  if (!url) return null;
  if (/^https?:\/\//.test(url) || url.startsWith("blob:") || url.startsWith("data:")) {
    return url;
  }
  return resolveMediaUrl(url);
}

function nowMs(): number {
  return Date.now();
}

interface Recording {
  item_id?: string;
  turn_id?: string;
  audio_blob_url: string;
  transcript: string;
  duration_seconds: number;
  attempt_number: number;
}

type Mode = "list" | "single" | "read" | "retell" | "role";

function detectMode(p: SpeakAndRecordPayload): Mode {
  if (p.turns && p.turns.length > 0) return "role";
  if (p.source_audio_url || p.source_audio_script) return "retell";
  if (p.text_to_read_aloud || p.passage || p.primary_text) return "read";
  if (
    (p.speaking_prompts && p.speaking_prompts.length > 0) ||
    (p.speaking_items && p.speaking_items.length > 0)
  ) return "list";
  return "single";
}

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

function extensionForMime(mime: string): string {
  if (mime.includes("ogg")) return ".ogg";
  if (mime.includes("mp4")) return ".mp4";
  return ".webm";
}

type SpeakItem = {
  id: string;
  label: string;
  kind: "prompt" | "turn";
  turn?: SpeakRoleplayTurn;
  sampleResponse?: string | null;
};

function buildSubmissionPayload(
  items: SpeakItem[],
  next: Record<string, Recording>,
  startedAt: number,
  pronunciation?: PronunciationResult | null
): Record<string, unknown> {
  return {
    recordings: items
      .map((it) => next[it.id])
      .filter(Boolean)
      .map((rec) => ({
        item_id: rec.item_id,
        turn_id: rec.turn_id,
        audio_blob_url: rec.audio_blob_url,
        duration_seconds: rec.duration_seconds,
        attempt_number: rec.attempt_number,
        transcript: rec.transcript,
      })),
    time_spent_seconds: Math.round((nowMs() - startedAt) / 1000),
    ...(pronunciation ? { pronunciation } : {}),
  };
}

export function SessionSpeakRecordWidget({ taskContent, disabled, onSubmit }: SessionWidgetProps) {
  const payload = taskContent as unknown as SpeakAndRecordPayload;
  const submitted = disabled;
  const mode = detectMode(payload);

  // Items: a unified list of "things to record".
  const items: Array<{ id: string; label: string; kind: "prompt" | "turn"; turn?: SpeakRoleplayTurn; sampleResponse?: string | null }> = (() => {
    if (mode === "role") {
      return (payload.turns ?? [])
        .filter((t) => t.speaker === "user")
        .map((t, i) => ({
          id: t.turn_id,
          label: payload.sample_user_responses?.[i] || "Your reply",
          kind: "turn" as const,
          turn: t,
          sampleResponse: payload.sample_user_responses?.[i] ?? null,
        }));
    }
    if (mode === "list") {
      const prompts = (
        payload.speaking_prompts && payload.speaking_prompts.length > 0
          ? payload.speaking_prompts
          : payload.speaking_items
      ) ?? [];
      return prompts.map((p, i) => ({
        id: `prompt_${i + 1}`,
        label: p,
        kind: "prompt" as const,
        sampleResponse: payload.sample_responses?.[i] ?? null,
      }));
    }
    if (mode === "read") {
      return [
        {
          id: "read_aloud",
          label: payload.text_to_read_aloud || payload.passage || payload.primary_text || "",
          kind: "prompt" as const,
          sampleResponse: payload.sample_response ?? null,
        },
      ];
    }
    if (mode === "retell") {
      return [
        {
          id: "retell",
          label: payload.retelling_prompt || "Retell what you heard in your own words.",
          kind: "prompt" as const,
          sampleResponse: payload.sample_response ?? null,
        },
      ];
    }
    return [
      {
        id: "prompt_1",
        label: payload.speaking_prompt || "Speaking prompt is missing.",
        kind: "prompt" as const,
        sampleResponse: payload.sample_response ?? null,
      },
    ];
  })();

  const startedAtRef = useRef<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordingStartedAtRef = useRef<number>(0);

  const [recordings, setRecordings] = useState<Record<string, Recording>>({});
  const [pronunciation, setPronunciation] = useState<PronunciationResult | null>(null);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [uploadingItemId, setUploadingItemId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [prepRemaining, setPrepRemaining] = useState(payload.preparation_seconds ?? 0);
  const sourceAudioUrl = resolveAudioUrl(payload.source_audio_url);
  const referenceAudioUrl = resolveAudioUrl(payload.reference_audio_url);

  useEffect(() => {
    if (!payload.preparation_seconds || submitted) return;
    if (prepRemaining <= 0) return;
    const interval = setInterval(() => {
      setPrepRemaining((s) => Math.max(0, s - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [payload.preparation_seconds, prepRemaining, submitted]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const handleSubmit = () => {
    const startedAt = startedAtRef.current ?? nowMs();
    startedAtRef.current = startedAt;
    const finalPayload = buildSubmissionPayload(items, recordings, startedAt, pronunciation);
    onSubmit(finalPayload);
  };

  const stopRecording = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  };

  const startRecording = async (itemId: string) => {
    if (submitted || activeItemId || uploadingItemId) return;
    if (prepRemaining > 0) return;
    setError(null);
    chunksRef.current = [];
    setActiveItemId(itemId);
    setElapsed(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      recorderRef.current = recorder;
      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        const duration = Math.round((nowMs() - recordingStartedAtRef.current) / 1000);
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setUploadingItemId(itemId);
        setActiveItemId(null);
        const usedMime = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: usedMime });
        const ext = extensionForMime(usedMime);
        try {
          const item = items.find((it) => it.id === itemId);
          
          let transcript = "";
          let audioUrl = "";

          if (mode === "read") {
            const refText = payload.text_to_read_aloud || payload.passage || payload.primary_text || "Empty";
            const wavBlob = await blobToWav(blob);
            const pronunResult = await sessionsApi.scorePronunciation(wavBlob, refText);
            setPronunciation(pronunResult);
            transcript = pronunResult.words.map(w => w.word).join(" ");
            audioUrl = ""; // No URL needed for simple read aloud pronunciation score
          } else {
            const result = await tasksApi.transcribeAudio(blob, `speak-${itemId}${ext}`);
            transcript = result.transcript;
            audioUrl = result.audio_url;
          }
          
          setRecordings((prev) => ({
            ...prev,
            [itemId]: {
              ...(item?.kind === "turn"
                ? { turn_id: itemId }
                : { item_id: itemId }),
              audio_blob_url: audioUrl,
              transcript: transcript,
              duration_seconds: duration,
              attempt_number: (prev[itemId]?.attempt_number ?? 0) + 1,
            },
          }));
        } catch {
          setError("Transcription failed. Please record that prompt again.");
        } finally {
          setUploadingItemId(null);
        }
      };
      recordingStartedAtRef.current = nowMs();
      recorder.start(250);
      const cap = Math.min(
        payload.speaking_duration_seconds || MAX_AUDIO_RECORDING_SECONDS,
        MAX_AUDIO_RECORDING_SECONDS,
      );
      timerRef.current = setInterval(() => {
        setElapsed((prev) => {
          const next = prev + 1;
          if (next >= cap) stopRecording();
          return next;
        });
      }, 1000);
    } catch {
      setActiveItemId(null);
      setError("Microphone access is needed for this speaking activity.");
    }
  };

  const allRecorded = items.every((it) => recordings[it.id]?.transcript?.trim());
  const missingSpeakingPrompt = mode === "single" && !payload.speaking_prompt?.trim();
  const canSubmit = (
    !submitted && !missingSpeakingPrompt && allRecorded && !activeItemId && !uploadingItemId
  );

  const cap = payload.speaking_duration_seconds || 60;

  return (
    <div className="tw-root">
      <TaskHeader
        topic={payload.topic_override || payload.topic || "Speaking Task"}
        intro={{
          title: payload.task_intro || "Record your response",
          body: payload.instructions_override || payload.instructions || "Tap the mic and speak naturally.",
        }}
        sub_skill={payload.sub_skill || ""}
        activity={payload.activity || "Speak & Record"}
        time={payload.estimated_time_minutes ?? 0}
      />

      {payload.grammar_rule_to_practice && (
        <div className="tw-rule-callout">
          <div className="tw-rule-icon">{I.rule}</div>
          <div className="tw-rule-body">
            <div className="tw-rule-label">Target rule</div>
            <div className="tw-rule-text">{payload.grammar_rule_to_practice}</div>
          </div>
        </div>
      )}

      {payload.target_pattern && (
        <div className="tw-rule-callout">
          <div className="tw-rule-icon">{I.rule}</div>
          <div className="tw-rule-body">
            <div className="tw-rule-label">Target pattern</div>
            <div className="tw-rule-text">{payload.target_pattern}</div>
          </div>
        </div>
      )}

      {payload.target_tone && (
        <div className="tw-rule-callout">
          <div className="tw-rule-icon">{I.rule}</div>
          <div className="tw-rule-body">
            <div className="tw-rule-label">Target tone</div>
            <div className="tw-rule-text">{payload.target_tone}</div>
          </div>
        </div>
      )}

      {mode === "retell" && sourceAudioUrl && (
        <div className="tw-card" style={{ background: "oklch(96% 0.03 245)" }}>
          <div className="tw-rule-label" style={{ marginBottom: 8 }}>Source audio</div>
          <audio src={sourceAudioUrl} controls style={{ width: "100%" }} />
        </div>
      )}

      {referenceAudioUrl && (
        <div className="tw-card" style={{ background: "oklch(96% 0.03 245)" }}>
          <div className="tw-rule-label" style={{ marginBottom: 8 }}>Reference pronunciation</div>
          <audio src={referenceAudioUrl} controls style={{ width: "100%" }} />
        </div>
      )}

      {/* Passage rendered in custom read layout below */}

      {payload.scenario_description && (
        <div
          className="tw-card"
          style={{ background: "oklch(96% 0.04 290)", borderColor: "oklch(82% 0.1 290)" }}
        >
          <div className="tw-rule-label" style={{ color: "oklch(40% 0.16 290)", marginBottom: 6 }}>
            Scenario
          </div>
          <div style={{ fontSize: 13.5, color: "var(--tw-navy)", lineHeight: 1.6 }}>
            {payload.scenario_description}
          </div>
        </div>
      )}

      {prepRemaining > 0 && !submitted && (
        <div className="tw-prep-countdown">
          {I.clock} Prep time · {formatDuration(prepRemaining)} left
        </div>
      )}

      {missingSpeakingPrompt && (
        <div
          style={{
            background: "oklch(96% 0.05 45)",
            border: "1px solid oklch(84% 0.1 45)",
            color: "oklch(35% 0.14 45)",
            borderRadius: 12,
            padding: "10px 12px",
            fontSize: 13,
            marginBottom: 14,
            lineHeight: 1.5,
          }}
        >
          This speaking activity is missing its prompt. Please refresh the activity.
        </div>
      )}

      {error && (
        <div
          style={{
            background: "oklch(96% 0.05 25)",
            border: "1px solid oklch(84% 0.1 25)",
            color: "oklch(35% 0.16 25)",
            borderRadius: 12,
            padding: "10px 12px",
            fontSize: 13,
            marginBottom: 14,
          }}
        >
          {error}
        </div>
      )}

      {mode === "read" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, marginBottom: 18 }}>
          {(payload.text_to_read_aloud || payload.passage || payload.primary_text) && (
            <div
              style={{
                background: "oklch(97% 0.02 245)",
                borderLeft: "3.5px solid oklch(60% 0.15 240)",
                borderRadius: 12,
                padding: "16px 20px",
                fontSize: 15,
                lineHeight: 1.8,
                color: "var(--tw-navy)",
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "oklch(55% 0.15 240)",
                  marginBottom: 8,
                  lineHeight: 1,
                }}
              >
                PASSAGE • {(payload.text_to_read_aloud || payload.passage || payload.primary_text || "").split(/\s+/).filter(Boolean).length} WORDS
              </div>
              <div>{payload.text_to_read_aloud || payload.passage || payload.primary_text}</div>
            </div>
          )}

          <div
            style={{
              background: "oklch(99% 0.01 140)",
              border: "1.5px solid oklch(85% 0.08 140)",
              borderRadius: 16,
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 16,
              textAlign: "center",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div
                style={{
                  color: "oklch(40% 0.12 140)",
                  fontWeight: 700,
                  fontSize: 13.5,
                  letterSpacing: 0.5,
                  textTransform: "uppercase",
                }}
              >
                READ THE PASSAGE ABOVE OUT LOUD
              </div>
              <div style={{ color: "var(--tw-ink-muted)", fontSize: 13 }}>
                We&apos;ll score pace, pronunciation, and word-stress.
              </div>
            </div>

            {(() => {
              const rec = recordings["read_aloud"];
              const isActive = activeItemId === "read_aloud";
              const isUploading = uploadingItemId === "read_aloud";
              const attemptsUsed = rec?.attempt_number ?? 0;
              const reRecordsLeft = Math.max(0, 3 - attemptsUsed);

              return (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, width: "100%" }}>
                  <button
                    type="button"
                    disabled={
                      submitted ||
                      missingSpeakingPrompt ||
                      !!uploadingItemId ||
                      (!!activeItemId && !isActive) ||
                      prepRemaining > 0
                    }
                    onClick={() => (isActive ? stopRecording() : startRecording("read_aloud"))}
                    className={`tw-mic-button${isActive ? " recording" : ""}`}
                    style={{
                      width: 72,
                      height: 72,
                      borderRadius: "50%",
                      backgroundColor: isActive ? "oklch(58% 0.2 15)" : "oklch(62% 0.17 145)",
                      color: "white",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      border: "none",
                      cursor: "pointer",
                      boxShadow: "0 6px 16px rgba(0,0,0,0.1)",
                      transition: "transform 0.2s, background-color 0.2s",
                    }}
                    aria-label={isActive ? "Stop recording" : "Start recording"}
                  >
                    {isActive ? I.stop : I.mic}
                  </button>

                  <div style={{ color: "var(--tw-navy)", fontSize: 14, fontWeight: 700 }}>
                    {isActive
                      ? `Recording ${formatDuration(elapsed)} / ${formatDuration(cap)}`
                      : isUploading
                      ? "Processing audio…"
                      : rec
                      ? `Recorded ${rec.duration_seconds}s · attempt ${attemptsUsed}/3`
                      : prepRemaining > 0
                      ? "Prep timer running…"
                      : "Tap to start reading"}
                  </div>

                  {rec && !submitted && reRecordsLeft > 0 && !activeItemId && !uploadingItemId && (
                    <button
                      className="tw-action-pill"
                      onClick={() => startRecording("read_aloud")}
                      style={{ marginTop: 4 }}
                    >
                      <span style={{ transform: "scaleX(-1)", display: "inline-block" }}>
                        {I.replay}
                      </span>{" "}
                      Re-record ({reRecordsLeft} left)
                    </button>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 14, marginBottom: 18 }}>
          {items.map((item, index) => {
            const rec = recordings[item.id];
            const isActive = activeItemId === item.id;
            const isUploading = uploadingItemId === item.id;
            const attemptsUsed = rec?.attempt_number ?? 0;
            const reRecordsLeft = Math.max(0, 3 - attemptsUsed);
            return (
              <div className="tw-card" key={item.id}>
                {mode === "role" && item.turn && (
                  <PriorRoleplayTurns
                    payload={payload}
                    thisTurnId={item.turn.turn_id}
                  />
                )}
                <div className="tw-q-number-row">
                  <div className="tw-q-number-badge">{index + 1}</div>
                  <div className="tw-q-stem">
                    {mode === "role"
                      ? "Your reply"
                      : item.label}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
                  <button
                    type="button"
                    disabled={
                      submitted ||
                      missingSpeakingPrompt ||
                      !!uploadingItemId ||
                      (!!activeItemId && !isActive) ||
                      prepRemaining > 0
                    }
                    onClick={() => (isActive ? stopRecording() : startRecording(item.id))}
                    className={`tw-mic-button${isActive ? " recording" : ""}`}
                    style={{ width: 56, height: 56 }}
                    aria-label={isActive ? "Stop recording" : "Start recording"}
                  >
                    {isActive ? I.stop : I.mic}
                  </button>
                  <div style={{ color: "var(--tw-ink-muted)", fontSize: 13, fontWeight: 700, flex: 1 }}>
                    {isActive
                      ? `Recording ${formatDuration(elapsed)} / ${formatDuration(cap)}`
                      : isUploading
                      ? "Processing audio…"
                      : rec
                      ? `Recorded ${rec.duration_seconds}s · attempt ${attemptsUsed}/3`
                      : prepRemaining > 0
                      ? "Prep timer running…"
                      : "Tap the mic to start"}
                  </div>
                  {rec && !submitted && reRecordsLeft > 0 && !activeItemId && !uploadingItemId && (
                    <button
                      className="tw-action-pill"
                      onClick={() => startRecording(item.id)}
                    >
                      <span style={{ transform: "scaleX(-1)", display: "inline-block" }}>
                        {I.replay}
                      </span>{" "}
                      Re-record ({reRecordsLeft} left)
                    </button>
                  )}
                </div>
                {rec && (
                  <div
                    style={{
                      marginTop: 12,
                      borderRadius: 12,
                      background: "oklch(96% 0.025 245)",
                      border: "1px solid oklch(86% 0.025 240)",
                      padding: "10px 12px",
                      color: "oklch(28% 0.07 240)",
                      fontSize: 13,
                      lineHeight: 1.6,
                    }}
                  >
                    <strong>Transcript:</strong> {rec.transcript || "(no speech detected)"}
                  </div>
                )}
                {submitted && item.sampleResponse && (
                  <div
                    style={{
                      marginTop: 10,
                      borderRadius: 12,
                      background: "oklch(94% 0.07 155)",
                      border: "1px solid oklch(80% 0.1 155)",
                      padding: "10px 12px",
                      color: "oklch(24% 0.1 155)",
                      fontSize: 13,
                      lineHeight: 1.6,
                    }}
                  >
                    <strong>Sample:</strong> {item.sampleResponse}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {submitted && mode !== "read" && payload.key_points_expected && payload.key_points_expected.length > 0 && (
        <div className="tw-hints-block" style={{ marginTop: 4 }}>
          <div className="tw-hints-label">Key points expected</div>
          <div className="tw-hints-list">
            {payload.key_points_expected.map((p, i) => (
               <div className="tw-hint-item" key={i}>
                <span className="tw-hint-dot" />
                {p}
              </div>
            ))}
          </div>
        </div>
      )}

      {submitted && payload.sample_talking_points && payload.sample_talking_points.length > 0 && (
        <div className="tw-hints-block" style={{ marginTop: 4 }}>
          <div className="tw-hints-label">Sample talking points</div>
          <div className="tw-hints-list">
            {payload.sample_talking_points.map((p, i) => (
              <div className="tw-hint-item" key={i}>
                <span className="tw-hint-dot" />
                {p}
              </div>
            ))}
          </div>
        </div>
      )}

      {!submitted && (
        <button
          className="tw-submit-btn"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          {I.send} Submit recordings
        </button>
      )}
    </div>
  );
}

function PriorRoleplayTurns({
  payload,
  thisTurnId,
}: {
  payload: SpeakAndRecordPayload;
  thisTurnId: string;
}) {
  const turns = payload.turns ?? [];
  const idx = turns.findIndex((t) => t.turn_id === thisTurnId);
  if (idx <= 0) return null;
  const priorAiTurn = [...turns.slice(0, idx)].reverse().find((t) => t.speaker === "ai");
  if (!priorAiTurn?.ai_line) return null;
  return (
    <div
      style={{
        background: "oklch(97% 0.02 245)",
        border: "1px dashed oklch(86% 0.025 240)",
        borderRadius: 10,
        padding: "8px 12px",
        marginBottom: 10,
        fontSize: 13,
        color: "var(--tw-navy)",
        lineHeight: 1.55,
      }}
    >
      <strong style={{ color: "oklch(48% 0.18 290)" }}>AI:</strong> {priorAiTurn.ai_line}
    </div>
  );
}
