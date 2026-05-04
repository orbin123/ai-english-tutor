"use client";

import { useState } from "react";
import type { ErrorSpottingTaskContent, GrammarRule } from "@/lib/tasks-api";

const ERROR_TYPE_LABELS: Record<string, string> = {
  past_simple: "Past Simple",
  past_continuous: "Past Continuous",
  present_simple: "Present Simple",
  present_perfect: "Present Perfect",
  past_perfect: "Past Perfect",
  future_simple: "Future Simple",
  subject_verb_agreement: "Subject-Verb Agreement",
  preposition: "Preposition",
  article: "Article",
  conditional: "Conditional",
  passive_voice: "Passive Voice",
  active_voice: "Active Voice",
  modal_verb: "Modal Verb",
  relative_clause: "Relative Clause",
  conjunction: "Conjunction",
};

interface Props {
  content: ErrorSpottingTaskContent;
  onSubmit: (answers: Record<string, string>) => void;
  isPending: boolean;
}

interface SentenceAnswer {
  verdict: "correct" | "has_error" | null;
  errorType: GrammarRule | null;
}

/**
 * Error Spotting task: show sentences, user toggles "Correct" / "Has error".
 * If "Has error" is selected, show a dropdown for picking the error type.
 */
export function GeneratedErrorSpotting({
  content,
  onSubmit,
  isPending,
}: Props) {
  const [answers, setAnswers] = useState<Record<string, SentenceAnswer>>({});

  const allAnswered = content.sentences.every((s) => {
    const a = answers[s.sentence_id];
    if (!a?.verdict) return false;
    if (a.verdict === "has_error" && !a.errorType) return false;
    return true;
  });

  const setVerdict = (id: string, verdict: "correct" | "has_error") => {
    setAnswers((prev) => ({
      ...prev,
      [id]: {
        verdict,
        errorType: verdict === "correct" ? null : prev[id]?.errorType ?? null,
      },
    }));
  };

  const setErrorType = (id: string, errorType: GrammarRule) => {
    setAnswers((prev) => ({
      ...prev,
      [id]: { ...prev[id], errorType },
    }));
  };

  const handleSubmit = () => {
    if (!allAnswered) return;
    // Flatten to { sentence_id: "correct" | "error_type" }
    const flat: Record<string, string> = {};
    content.sentences.forEach((s) => {
      const a = answers[s.sentence_id];
      flat[s.sentence_id] =
        a.verdict === "correct" ? "correct" : (a.errorType ?? "unknown");
    });
    onSubmit(flat);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Task intro */}
      <p
        style={{
          fontSize: 14,
          color: "oklch(40% 0.07 240)",
          lineHeight: 1.6,
          margin: 0,
        }}
      >
        {content.task_intro}
      </p>
      <p
        style={{
          fontSize: 13,
          color: "oklch(45% 0.07 240)",
          margin: 0,
          fontStyle: "italic",
        }}
      >
        {content.instructions}
      </p>

      {/* Sentences */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {content.sentences.map((sent, i) => {
          const a = answers[sent.sentence_id];
          return (
            <div
              key={sent.sentence_id}
              style={{
                background: "rgba(255,255,255,0.85)",
                backdropFilter: "blur(16px)",
                WebkitBackdropFilter: "blur(16px)",
                borderRadius: 14,
                border: a?.verdict
                  ? a.verdict === "correct"
                    ? "1.5px solid oklch(55% 0.18 155)"
                    : "1.5px solid oklch(58% 0.2 15)"
                  : "1px solid rgba(80,120,200,0.12)",
                padding: "18px 20px",
                transition: "all 0.2s ease",
              }}
            >
              {/* Sentence */}
              <p
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "oklch(20% 0.07 240)",
                  margin: "0 0 14px",
                  lineHeight: 1.6,
                }}
              >
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 24,
                    height: 24,
                    borderRadius: "50%",
                    background: "oklch(52% 0.18 240)",
                    color: "white",
                    fontSize: 12,
                    fontWeight: 700,
                    marginRight: 10,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                {sent.sentence}
              </p>

              {/* Toggle buttons */}
              <div style={{ display: "flex", gap: 8, marginBottom: a?.verdict === "has_error" ? 12 : 0 }}>
                <button
                  type="button"
                  onClick={() => setVerdict(sent.sentence_id, "correct")}
                  style={{
                    flex: 1,
                    padding: "9px 14px",
                    borderRadius: 10,
                    border:
                      a?.verdict === "correct"
                        ? "1.5px solid oklch(55% 0.18 155)"
                        : "1px solid rgba(80,120,200,0.15)",
                    background:
                      a?.verdict === "correct"
                        ? "oklch(93% 0.04 155)"
                        : "rgba(255,255,255,0.9)",
                    color:
                      a?.verdict === "correct"
                        ? "oklch(30% 0.12 155)"
                        : "oklch(25% 0.07 240)",
                    fontSize: 13,
                    fontWeight: a?.verdict === "correct" ? 600 : 500,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  ✓ Correct
                </button>
                <button
                  type="button"
                  onClick={() => setVerdict(sent.sentence_id, "has_error")}
                  style={{
                    flex: 1,
                    padding: "9px 14px",
                    borderRadius: 10,
                    border:
                      a?.verdict === "has_error"
                        ? "1.5px solid oklch(58% 0.2 15)"
                        : "1px solid rgba(80,120,200,0.15)",
                    background:
                      a?.verdict === "has_error"
                        ? "oklch(95% 0.04 15)"
                        : "rgba(255,255,255,0.9)",
                    color:
                      a?.verdict === "has_error"
                        ? "oklch(38% 0.12 15)"
                        : "oklch(25% 0.07 240)",
                    fontSize: 13,
                    fontWeight: a?.verdict === "has_error" ? 600 : 500,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                >
                  ✗ Has error
                </button>
              </div>

              {/* Error type dropdown */}
              {a?.verdict === "has_error" && (
                <div style={{ animation: "fadeSlideUp 0.2s ease both" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: 12,
                      fontWeight: 600,
                      color: "oklch(40% 0.07 240)",
                      marginBottom: 6,
                    }}
                  >
                    What type of error?
                  </label>
                  <select
                    value={a.errorType ?? ""}
                    onChange={(e) =>
                      setErrorType(
                        sent.sentence_id,
                        e.target.value as GrammarRule,
                      )
                    }
                    style={{
                      width: "100%",
                      padding: "10px 14px",
                      borderRadius: 10,
                      border: "1px solid rgba(80,120,200,0.18)",
                      background: "rgba(255,255,255,0.95)",
                      color: "oklch(20% 0.07 240)",
                      fontSize: 13,
                      fontWeight: 500,
                      appearance: "none",
                      WebkitAppearance: "none",
                      cursor: "pointer",
                    }}
                  >
                    <option value="" disabled>
                      Select error type…
                    </option>
                    {Object.entries(ERROR_TYPE_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Submit */}
      <button
        type="button"
        disabled={!allAnswered || isPending}
        onClick={handleSubmit}
        style={{
          width: "100%",
          padding: "14px 0",
          borderRadius: 12,
          border: "none",
          background: allAnswered
            ? "oklch(52% 0.18 240)"
            : "oklch(85% 0.03 240)",
          color: allAnswered ? "white" : "oklch(55% 0.05 240)",
          fontSize: 15,
          fontWeight: 700,
          cursor: allAnswered ? "pointer" : "not-allowed",
          transition: "all 0.2s ease",
          opacity: isPending ? 0.6 : 1,
        }}
      >
        {isPending ? "Submitting…" : "Submit answers"}
      </button>
    </div>
  );
}
