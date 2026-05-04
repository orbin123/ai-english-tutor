"use client";

import { useState } from "react";
import type { ErrorCorrectionTaskContent } from "@/lib/tasks-api";

interface Props {
  content: ErrorCorrectionTaskContent;
  onSubmit: (answers: Record<string, string>) => void;
  isPending: boolean;
}

/**
 * Error Correction task: show an incorrect sentence,
 * user types the corrected version.
 */
export function GeneratedErrorCorrection({
  content,
  onSubmit,
  isPending,
}: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const allAnswered = content.items.every(
    (item) => (answers[item.item_id] ?? "").trim().length > 0,
  );

  const handleChange = (id: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  };

  const handleSubmit = () => {
    if (!allAnswered) return;
    onSubmit(answers);
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

      {/* Items */}
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {content.items.map((item, i) => (
          <div
            key={item.item_id}
            style={{
              background: "rgba(255,255,255,0.85)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              borderRadius: 14,
              border: "1px solid rgba(80,120,200,0.12)",
              padding: "18px 20px",
              transition: "all 0.2s ease",
            }}
          >
            {/* Number + error type badge */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 12,
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
                  background: "oklch(58% 0.2 15)",
                  color: "white",
                  fontSize: 12,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {i + 1}
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "oklch(45% 0.15 15)",
                  background: "oklch(95% 0.04 15)",
                  padding: "3px 10px",
                  borderRadius: 20,
                }}
              >
                {item.error_type.replace(/_/g, " ")}
              </span>
            </div>

            {/* Incorrect sentence with strikethrough hint */}
            <blockquote
              style={{
                margin: "0 0 10px 0",
                padding: "12px 16px",
                borderRadius: 10,
                background: "oklch(97% 0.01 15)",
                borderLeft: "3px solid oklch(58% 0.2 15)",
                fontSize: 14,
                color: "oklch(30% 0.08 15)",
                lineHeight: 1.6,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "oklch(55% 0.15 15)",
                  display: "block",
                  marginBottom: 4,
                }}
              >
                Incorrect
              </span>
              {item.incorrect_sentence}
            </blockquote>

            {/* Text input */}
            <input
              type="text"
              value={answers[item.item_id] ?? ""}
              onChange={(e) => handleChange(item.item_id, e.target.value)}
              placeholder="Rewrite the sentence correctly…"
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: 10,
                border: "1px solid rgba(80,120,200,0.18)",
                background: "rgba(255,255,255,0.95)",
                color: "oklch(18% 0.07 240)",
                fontSize: 14,
                fontWeight: 500,
                fontFamily: "'Plus Jakarta Sans', sans-serif",
                boxSizing: "border-box",
              }}
            />
          </div>
        ))}
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
