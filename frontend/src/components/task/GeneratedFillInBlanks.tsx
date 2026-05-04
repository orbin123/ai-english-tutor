"use client";

import { useState } from "react";
import type { FillInBlanksTaskContent } from "@/lib/tasks-api";

interface Props {
  content: FillInBlanksTaskContent;
  onSubmit: (answers: Record<string, string>) => void;
  isPending: boolean;
}

/**
 * Generated Fill-in-Blanks task renderer.
 *
 * Displays the passage, highlights blanks inline, and shows
 * 4 multiple-choice option buttons per blank. One click picks it;
 * Submit is only active when all blanks are answered.
 */
export function GeneratedFillInBlanks({ content, onSubmit, isPending }: Props) {
  const [selected, setSelected] = useState<Record<string, string>>({});
  const allAnswered = content.blanks.every((b) => selected[b.blank_id]);

  const handlePick = (blankId: string, option: string) => {
    setSelected((prev) => ({ ...prev, [blankId]: option }));
  };

  const handleSubmit = () => {
    if (!allAnswered) return;
    onSubmit(selected);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Passage title */}
      <h2
        style={{
          fontSize: 20,
          fontWeight: 700,
          color: "oklch(15% 0.09 245)",
          margin: 0,
          letterSpacing: "-0.02em",
        }}
      >
        {content.passage_title}
      </h2>

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

      {/* Passage card */}
      <div
        style={{
          background: "oklch(96% 0.015 240)",
          borderRadius: 12,
          padding: "20px 22px",
          border: "1px solid rgba(80,120,200,0.1)",
          fontSize: 15,
          lineHeight: 1.8,
          color: "oklch(22% 0.07 240)",
        }}
      >
        {content.passage}
      </div>

      {/* Blanks with options */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {content.blanks.map((blank, i) => (
          <div
            key={blank.blank_id}
            style={{
              background: "rgba(255,255,255,0.85)",
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              borderRadius: 14,
              border: selected[blank.blank_id]
                ? "1.5px solid oklch(60% 0.15 240)"
                : "1px solid rgba(80,120,200,0.12)",
              padding: "18px 20px",
              transition: "border-color 0.2s ease, box-shadow 0.2s ease",
              boxShadow: selected[blank.blank_id]
                ? "0 2px 16px rgba(80,130,220,0.1)"
                : "none",
            }}
          >
            {/* Sentence with blank */}
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
                }}
              >
                {i + 1}
              </span>
              {blank.sentence_with_blank}
            </p>

            {/* Options grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 8,
              }}
            >
              {blank.options.map((opt) => {
                const isSelected = selected[blank.blank_id] === opt;
                return (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => handlePick(blank.blank_id, opt)}
                    style={{
                      padding: "10px 14px",
                      borderRadius: 10,
                      border: isSelected
                        ? "1.5px solid oklch(52% 0.18 240)"
                        : "1px solid rgba(80,120,200,0.15)",
                      background: isSelected
                        ? "oklch(93% 0.04 240)"
                        : "rgba(255,255,255,0.9)",
                      color: isSelected
                        ? "oklch(30% 0.12 240)"
                        : "oklch(25% 0.07 240)",
                      fontSize: 14,
                      fontWeight: isSelected ? 600 : 500,
                      cursor: "pointer",
                      transition:
                        "all 0.15s ease",
                      textAlign: "left",
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) {
                        e.currentTarget.style.background = "oklch(96% 0.02 240)";
                        e.currentTarget.style.borderColor = "rgba(80,120,200,0.25)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) {
                        e.currentTarget.style.background = "rgba(255,255,255,0.9)";
                        e.currentTarget.style.borderColor = "rgba(80,120,200,0.15)";
                      }
                    }}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>

            {/* Grammar rule badge */}
            <div style={{ marginTop: 10 }}>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "oklch(50% 0.12 240)",
                  background: "oklch(95% 0.02 240)",
                  padding: "2px 8px",
                  borderRadius: 6,
                }}
              >
                {blank.grammar_rule.replace(/_/g, " ")}
              </span>
            </div>
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
