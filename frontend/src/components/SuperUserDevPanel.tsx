"use client";

import { useState, useRef, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { tasksApi } from "@/lib/tasks-api";

// ─────────────────────────────────────────────────────────────────
// Curriculum constants (mirrored from backend — do NOT fetch)
// ─────────────────────────────────────────────────────────────────

const WEEK_SCHEDULE: Record<number, string> = {
  1: "grammar",
  2: "vocabulary",
  3: "expression",
  4: "comprehension",
  5: "tone",
  6: "grammar",
  7: "vocabulary",
};

const SKILL_ACTIVITIES: Record<string, string[]> = {
  grammar: ["reading", "writing", "speaking"],
  vocabulary: ["reading", "writing", "speaking"],
  expression: ["reading", "writing", "speaking"],
  comprehension: ["reading", "listening"],
  tone: ["reading", "writing", "speaking"],
};

const TASK_TYPES = [
  // Grammar — reading
  { id: "fill_in_blanks", label: "Fill in blanks", skill: "grammar", activity: "reading" },
  { id: "error_spotting", label: "Error spotting", skill: "grammar", activity: "reading" },
  // Grammar — writing
  { id: "sentence_transformation", label: "Sentence transform", skill: "grammar", activity: "writing" },
  { id: "voice_conversion", label: "Voice conversion", skill: "grammar", activity: "writing" },
  { id: "error_correction", label: "Error correction", skill: "grammar", activity: "writing" },
  // Grammar — speaking
  { id: "speak_with_tense", label: "Speak with tense", skill: "grammar", activity: "speaking" },
  { id: "speak_sentence_combiners", label: "Sentence combiners", skill: "grammar", activity: "speaking" },
  // Vocabulary — reading
  { id: "word_meaning_match", label: "Word meaning match", skill: "vocabulary", activity: "reading" },
  { id: "context_mcq", label: "Context MCQ", skill: "vocabulary", activity: "reading" },
  // Vocabulary — writing
  { id: "word_upgrade", label: "Word upgrade", skill: "vocabulary", activity: "writing" },
  { id: "vocab_paraphrase", label: "Vocab paraphrase", skill: "vocabulary", activity: "writing" },
  { id: "conciseness_rewrite", label: "Conciseness rewrite", skill: "vocabulary", activity: "writing" },
  // Expression — reading
  { id: "passage_summarization", label: "Passage summary", skill: "expression", activity: "reading" },
  { id: "structure_identification", label: "Structure ID", skill: "expression", activity: "reading" },
  // Expression — writing
  { id: "structured_essay", label: "Structured essay", skill: "expression", activity: "writing" },
  { id: "idea_paraphrasing", label: "Idea paraphrasing", skill: "expression", activity: "writing" },
  // Comprehension — reading
  { id: "reading_comprehension_mcq", label: "Reading comp. MCQ", skill: "comprehension", activity: "reading" },
  { id: "true_false_not_given", label: "True/False/Not given", skill: "comprehension", activity: "reading" },
  // Comprehension — listening
  { id: "audio_mcq", label: "Audio MCQ", skill: "comprehension", activity: "listening" },
  { id: "cloze_listening", label: "Cloze listening", skill: "comprehension", activity: "listening" },
  // Tone — reading
  { id: "tone_identification", label: "Tone identification", skill: "tone", activity: "reading" },
  { id: "message_to_scenario", label: "Message to scenario", skill: "tone", activity: "reading" },
  // Tone — writing
  { id: "register_conversion", label: "Register conversion", skill: "tone", activity: "writing" },
  { id: "tone_response", label: "Tone response", skill: "tone", activity: "writing" },
  // Tone — speaking
  { id: "roleplay_scenario", label: "Roleplay scenario", skill: "tone", activity: "speaking" },
] as const;

type TaskTypeEntry = (typeof TASK_TYPES)[number];

interface DaySlot {
  week: number;
  day: number;
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────

function computeAvailableDays(
  taskType: TaskTypeEntry,
  courseDuration: number,
): DaySlot[] {
  const { skill, activity } = taskType;

  // Which day-in-week numbers map to this skill?
  const skillDays = Object.entries(WEEK_SCHEDULE)
    .filter(([, s]) => s === skill)
    .map(([d]) => Number(d));

  // For each skill-day, which day-in-week index does this activity fall on?
  // Activities rotate by day within that week-day: day 1 = activity[0], etc.
  // But the schedule maps day-of-week (1-7) to skill. Activities for that
  // skill are rotated across the skill-days in the week.
  // For simplicity: the activity index is the position in SKILL_ACTIVITIES[skill]
  const activities = SKILL_ACTIVITIES[skill];
  const activityIdx = activities.indexOf(activity);
  if (activityIdx === -1) return [];

  const result: DaySlot[] = [];
  for (let week = 1; week <= courseDuration; week++) {
    // For each day-of-week that belongs to this skill, determine which
    // activity index it rotates to. The rotation is: skillDays[i] maps
    // to activities[i % activities.length].
    skillDays.forEach((d, i) => {
      if (i % activities.length === activityIdx) {
        result.push({ week, day: d });
      }
    });
  }
  return result;
}

function daySlotKey(s: DaySlot): string {
  return `${s.week}-${s.day}`;
}

// ─────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────

export function SuperUserDevPanel() {
  const isSuperUser = useAuthStore((s) => s.isSuperUser);
  if (!isSuperUser) return null;
  return <PanelInner />;
}

function PanelInner() {
  const router = useRouter();

  // ── Position / drag ────────────────────────────────────────
  const [pos, setPos] = useState({ x: 20, y: 20 }); // offset from bottom-right
  const [isMinimized, setIsMinimized] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragOrigin = useRef({ mouseX: 0, mouseY: 0, startX: 0, startY: 0 });

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);
      dragOrigin.current = {
        mouseX: e.clientX,
        mouseY: e.clientY,
        startX: pos.x,
        startY: pos.y,
      };

      const onMove = (ev: MouseEvent) => {
        const dx = ev.clientX - dragOrigin.current.mouseX;
        const dy = ev.clientY - dragOrigin.current.mouseY;
        setPos({
          x: dragOrigin.current.startX - dx,
          y: dragOrigin.current.startY + dy,
        });
      };
      const onUp = () => {
        setIsDragging(false);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [pos],
  );

  // ── State ──────────────────────────────────────────────────
  const [courseDuration, setCourseDuration] = useState<24 | 48>(24);
  const [selectedType, setSelectedType] = useState<TaskTypeEntry | null>(null);
  const [selectedDay, setSelectedDay] = useState<DaySlot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const availableDays = useMemo(
    () => (selectedType ? computeAvailableDays(selectedType, courseDuration) : []),
    [selectedType, courseDuration],
  );

  const handleTypeSelect = (t: TaskTypeEntry) => {
    setSelectedType(t);
    setSelectedDay(null);
    setError(null);
  };

  const handleGo = async () => {
    if (!selectedDay || !selectedType) return;
    setIsLoading(true);
    setError(null);
    try {
      const bundle = await tasksApi.superuserJump(selectedDay.week, selectedDay.day);
      sessionStorage.setItem("superuser_jump_bundle", JSON.stringify(bundle));
      router.push("/task");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Jump failed";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Styles ─────────────────────────────────────────────────
  const S = {
    panel: {
      position: "fixed" as const,
      bottom: pos.y,
      right: pos.x,
      width: 380,
      zIndex: 9999,
      fontFamily: "system-ui, -apple-system, sans-serif",
      fontSize: 12,
      borderRadius: 12,
      border: "0.5px solid #d4d4d8",
      background: "#fff",
      boxShadow: "0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)",
      overflow: "hidden" as const,
      userSelect: "none" as const,
    },
    header: {
      display: "flex" as const,
      alignItems: "center" as const,
      justifyContent: "space-between" as const,
      padding: "8px 12px",
      background: "#fafafa",
      borderBottom: "0.5px solid #e4e4e7",
      cursor: isDragging ? "grabbing" : "grab",
    },
    headerLeft: {
      display: "flex" as const,
      alignItems: "center" as const,
      gap: 8,
    },
    redDot: {
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: "#FF5F57",
      flexShrink: 0,
    },
    headerLabel: {
      fontSize: 12,
      fontWeight: 700 as const,
      color: "#18181b",
      letterSpacing: "-0.01em",
    },
    badge: {
      fontSize: 9,
      fontWeight: 700 as const,
      letterSpacing: "0.06em",
      color: "#7C3AED",
      background: "#EDE9FE",
      padding: "2px 6px",
      borderRadius: 4,
      textTransform: "uppercase" as const,
    },
    toggleBtn: {
      border: "none",
      background: "none",
      cursor: "pointer",
      fontSize: 14,
      color: "#71717a",
      padding: "2px 4px",
      lineHeight: 1,
    },
    body: {
      padding: "10px 12px 12px",
      display: "flex" as const,
      flexDirection: "column" as const,
      gap: 10,
    },
    sectionLabel: {
      fontSize: 10,
      fontWeight: 700 as const,
      color: "#a1a1aa",
      letterSpacing: "0.08em",
      textTransform: "uppercase" as const,
      margin: 0,
    },
    pillWrap: {
      display: "flex" as const,
      flexWrap: "wrap" as const,
      gap: 4,
    },
    divider: {
      height: 1,
      background: "#f4f4f5",
      border: "none",
      margin: "2px 0",
    },
  };

  const pillStyle = (selected: boolean): React.CSSProperties => ({
    fontSize: 11,
    fontWeight: selected ? 600 : 500,
    padding: "3px 10px",
    borderRadius: 999,
    border: selected ? "1px solid #AFA9EC" : "1px solid #e4e4e7",
    background: selected ? "#EEEDFE" : "#fff",
    color: selected ? "#3C3489" : "#52525b",
    cursor: "pointer",
    transition: "all 0.12s ease",
    lineHeight: "18px",
    whiteSpace: "nowrap" as const,
  });

  const chipStyle = (selected: boolean): React.CSSProperties => ({
    fontSize: 10,
    fontWeight: selected ? 600 : 500,
    padding: "2px 7px",
    borderRadius: 6,
    border: selected ? "1px solid #AFA9EC" : "1px solid #e4e4e7",
    background: selected ? "#EEEDFE" : "#fafafa",
    color: selected ? "#3C3489" : "#71717a",
    cursor: "pointer",
    transition: "all 0.12s ease",
    lineHeight: "16px",
    whiteSpace: "nowrap" as const,
  });

  const courseBtnStyle = (active: boolean): React.CSSProperties => ({
    fontSize: 11,
    fontWeight: active ? 700 : 500,
    padding: "3px 12px",
    borderRadius: 6,
    border: active ? "1px solid #AFA9EC" : "1px solid #e4e4e7",
    background: active ? "#EEEDFE" : "#fff",
    color: active ? "#3C3489" : "#71717a",
    cursor: "pointer",
    transition: "all 0.12s ease",
  });

  const chainBadge = (bg: string, color: string): React.CSSProperties => ({
    fontSize: 10,
    fontWeight: 600,
    padding: "2px 8px",
    borderRadius: 4,
    background: bg,
    color,
    whiteSpace: "nowrap" as const,
  });

  return (
    <div style={S.panel}>
      {/* ── Header ──────────────────────────────────── */}
      <div style={S.header} onMouseDown={onMouseDown}>
        <div style={S.headerLeft}>
          <div style={S.redDot} />
          <span style={S.headerLabel}>Dev panel</span>
          <span style={S.badge}>Superuser</span>
        </div>
        <button
          style={S.toggleBtn}
          onClick={() => setIsMinimized((v) => !v)}
          aria-label={isMinimized ? "Expand panel" : "Minimize panel"}
        >
          {isMinimized ? "▲" : "▼"}
        </button>
      </div>

      {/* ── Body ────────────────────────────────────── */}
      {!isMinimized && (
        <div style={S.body}>
          {/* Course duration selector */}
          <div>
            <p style={{ ...S.sectionLabel, marginBottom: 6 }}>Course</p>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                style={courseBtnStyle(courseDuration === 24)}
                onClick={() => { setCourseDuration(24); setSelectedDay(null); }}
              >
                24-week
              </button>
              <button
                style={courseBtnStyle(courseDuration === 48)}
                onClick={() => { setCourseDuration(48); setSelectedDay(null); }}
              >
                48-week
              </button>
            </div>
          </div>

          <hr style={S.divider} />

          {/* Task type pills */}
          <div>
            <p style={{ ...S.sectionLabel, marginBottom: 6 }}>Task type</p>
            <div style={S.pillWrap}>
              {TASK_TYPES.map((t) => (
                <button
                  key={t.id}
                  style={pillStyle(selectedType?.id === t.id)}
                  onClick={() => handleTypeSelect(t)}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chain info row */}
          {selectedType && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                <span style={chainBadge("#DCFCE7", "#166534")}>
                  {selectedType.skill}
                </span>
                <span style={{ color: "#d4d4d8", fontSize: 11 }}>›</span>
                <span style={chainBadge("#FEF3C7", "#92400E")}>
                  {selectedType.activity}
                </span>
                <span style={{ color: "#d4d4d8", fontSize: 11 }}>›</span>
                <span style={chainBadge("#EEEDFE", "#3C3489")}>
                  {selectedType.label}
                </span>
              </div>

              <hr style={S.divider} />

              {/* Day chips */}
              <div>
                <p style={{ ...S.sectionLabel, marginBottom: 4 }}>
                  {availableDays.length} days available — pick one
                </p>
                <div
                  style={{
                    maxHeight: 130,
                    overflowY: "auto",
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 4,
                    padding: "2px 0",
                  }}
                >
                  {availableDays.map((slot) => {
                    const key = daySlotKey(slot);
                    const isSelected =
                      selectedDay != null && daySlotKey(selectedDay) === key;
                    return (
                      <button
                        key={key}
                        style={chipStyle(isSelected)}
                        onClick={() => { setSelectedDay(slot); setError(null); }}
                      >
                        W{slot.week} D{slot.day}
                      </button>
                    );
                  })}
                </div>
              </div>

              <hr style={S.divider} />

              {/* Go button row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    color: selectedDay ? "#18181b" : "#a1a1aa",
                    fontWeight: 500,
                  }}
                >
                  {selectedDay
                    ? `Week ${selectedDay.week}, Day ${selectedDay.day} → ${selectedType.label}`
                    : "No day selected"}
                </span>
                <button
                  onClick={handleGo}
                  disabled={!selectedDay || isLoading}
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "5px 14px",
                    borderRadius: 6,
                    border: "none",
                    background:
                      !selectedDay || isLoading ? "#e4e4e7" : "#7C3AED",
                    color: !selectedDay || isLoading ? "#a1a1aa" : "#fff",
                    cursor:
                      !selectedDay || isLoading ? "not-allowed" : "pointer",
                    transition: "all 0.15s ease",
                    whiteSpace: "nowrap",
                  }}
                >
                  {isLoading ? "Jumping…" : "Go →"}
                </button>
              </div>

              {/* Error message */}
              {error && (
                <p
                  style={{
                    fontSize: 11,
                    color: "#DC2626",
                    background: "#FEF2F2",
                    padding: "4px 8px",
                    borderRadius: 6,
                    margin: 0,
                  }}
                >
                  {error}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
