"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const ACCENT_HUE = 240;
const CTA_TEXT = "Start Learning Free";
const HERO_HEADLINE = "Stop Practicing English.\nStart Improving It.";

// ── Glassmorphism card ──────────────────────────────────────────────────────
function GlassCard({
  children,
  style,
  className,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}) {
  return (
    <div
      className={className}
      style={{
        background: "rgba(255,255,255,0.6)",
        backdropFilter: "blur(18px)",
        WebkitBackdropFilter: "blur(18px)",
        border: "1.5px solid rgba(255,255,255,0.88)",
        borderRadius: 20,
        boxShadow:
          "0 4px 32px rgba(100,140,210,0.13), 0 1.5px 6px rgba(80,120,200,0.07)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── Dot grid texture ────────────────────────────────────────────────────────
function DotGrid({ opacity = 0.18 }: { opacity?: number }) {
  return (
    <svg
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
      aria-hidden
    >
      <defs>
        <pattern
          id="dots"
          x="0"
          y="0"
          width="22"
          height="22"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="2" cy="2" r="1.1" fill={`rgba(90,130,210,${opacity})`} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#dots)" />
    </svg>
  );
}

// ── NAV ─────────────────────────────────────────────────────────────────────
function Nav({ onCTAClick }: { onCTAClick: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", h);
    return () => window.removeEventListener("scroll", h);
  }, []);
  return (
    <nav
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        padding: "0 40px",
        transition: "all 0.3s",
        background: scrolled ? "rgba(220,235,250,0.82)" : "transparent",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        borderBottom: scrolled ? "1px solid rgba(255,255,255,0.7)" : "none",
      }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          height: 68,
          gap: 40,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 9,
              background: `oklch(52% 0.18 ${ACCENT_HUE})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
              <path
                d="M3 13L8.5 4L14 13"
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M5.2 10h6.6"
                stroke="white"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <span
            style={{
              fontWeight: 700,
              fontSize: 17,
              letterSpacing: "-0.3px",
              color: "oklch(18% 0.09 245)",
            }}
          >
            LingosAI
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
          {["Features", "How It Works", "Pricing", "For Teams"].map((l) => (
            <a
              key={l}
              href="#"
              style={{
                padding: "7px 16px",
                borderRadius: 50,
                fontSize: 14,
                fontWeight: 500,
                color: "oklch(28% 0.08 240)",
                textDecoration: "none",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) =>
                ((e.target as HTMLElement).style.background =
                  "rgba(255,255,255,0.5)")
              }
              onMouseLeave={(e) =>
                ((e.target as HTMLElement).style.background = "transparent")
              }
            >
              {l}
            </a>
          ))}
        </div>
        <button
          onClick={onCTAClick}
          style={{
            padding: "9px 22px",
            borderRadius: 50,
            border: "none",
            cursor: "pointer",
            background: `oklch(22% 0.09 ${ACCENT_HUE})`,
            color: "white",
            fontFamily: "inherit",
            fontWeight: 600,
            fontSize: 14,
            boxShadow: "0 2px 12px rgba(30,60,120,0.18)",
            transition: "transform 0.15s, box-shadow 0.15s",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.transform = "scale(1.04)";
            (e.currentTarget as HTMLElement).style.boxShadow =
              "0 4px 18px rgba(30,60,120,0.28)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.transform = "scale(1)";
            (e.currentTarget as HTMLElement).style.boxShadow =
              "0 2px 12px rgba(30,60,120,0.18)";
          }}
        >
          {CTA_TEXT}
        </button>
      </div>
    </nav>
  );
}

// ── Chat bubble ──────────────────────────────────────────────────────────────
function ChatBubble({
  role,
  children,
  visible,
}: {
  role: "ai" | "user";
  children: React.ReactNode;
  delay?: number;
  visible: boolean;
}) {
  const isAI = role === "ai";
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        flexDirection: isAI ? "row" : "row-reverse",
        opacity: visible ? 1 : 0,
        animation: visible ? "fadeSlideUp 0.55s ease forwards" : "none",
        flexShrink: 0,
      }}
    >
      {isAI && (
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 9,
            flexShrink: 0,
            background: "oklch(52% 0.18 240)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginTop: 2,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M2 11L7 3L12 11"
              stroke="white"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M4 8.5h6"
              stroke="white"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </div>
      )}
      <div
        style={{
          background: isAI ? "rgba(255,255,255,0.85)" : "oklch(52% 0.18 240)",
          color: isAI ? "oklch(18% 0.07 240)" : "white",
          padding: "10px 14px",
          borderRadius: isAI ? "4px 14px 14px 14px" : "14px 4px 14px 14px",
          fontSize: 13,
          lineHeight: 1.6,
          maxWidth: 260,
          border: isAI ? "1px solid rgba(255,255,255,0.9)" : "none",
          backdropFilter: "blur(10px)",
          boxShadow: "0 2px 12px rgba(80,120,200,0.1)",
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ── Feedback highlight ───────────────────────────────────────────────────────
function FeedbackCard() {
  return (
    <GlassCard style={{ padding: 18, fontSize: 13 }}>
      <div
        style={{
          fontWeight: 600,
          color: "oklch(40% 0.1 240)",
          marginBottom: 10,
          fontSize: 12,
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        AI Feedback
      </div>
      <div
        style={{ lineHeight: 1.7, color: "oklch(25% 0.07 240)" }}
      >
        &ldquo;I{" "}
        <span
          style={{
            background: "rgba(220,60,60,0.12)",
            borderBottom: "2px solid rgba(220,60,60,0.5)",
            borderRadius: 2,
          }}
        >
          am study
        </span>{" "}
        English every day.&rdquo;
      </div>
      <div
        style={{
          marginTop: 12,
          padding: "10px 12px",
          borderRadius: 10,
          background: "rgba(200,230,255,0.5)",
          border: "1px solid rgba(160,200,255,0.4)",
        }}
      >
        <div
          style={{
            fontWeight: 600,
            color: "oklch(35% 0.12 240)",
            fontSize: 12,
            marginBottom: 4,
          }}
        >
          ⚠ Grammar Error
        </div>
        <div
          style={{
            color: "oklch(30% 0.08 240)",
            fontSize: 12,
            lineHeight: 1.6,
          }}
        >
          Use present continuous correctly:{" "}
          <strong>&ldquo;I am studying&rdquo;</strong> — the verb requires the
          -ing form after &ldquo;am&rdquo;.
        </div>
      </div>
      <div
        style={{
          marginTop: 8,
          padding: "8px 12px",
          borderRadius: 10,
          background: "rgba(180,230,200,0.4)",
          border: "1px solid rgba(130,200,160,0.4)",
        }}
      >
        <div
          style={{
            fontWeight: 600,
            color: "oklch(35% 0.12 145)",
            fontSize: 12,
            marginBottom: 3,
          }}
        >
          ✓ Better version
        </div>
        <div style={{ color: "oklch(28% 0.08 145)", fontSize: 12 }}>
          &ldquo;I am studying English every day.&rdquo;
        </div>
      </div>
    </GlassCard>
  );
}

// ── Skill radar ─────────────────────────────────────────────────────────────
function RadarChart({
  skills,
}: {
  skills: { label: string; val: number }[];
}) {
  const cx = 90,
    cy = 90,
    r = 68;
  const n = skills.length;
  const pts = (level: number) =>
    skills.map((_, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
      const d = r * level;
      return [cx + d * Math.cos(angle), cy + d * Math.sin(angle)];
    });
  const toPath = (p: number[][]) =>
    p.map((pt, i) => `${i === 0 ? "M" : "L"}${pt[0]},${pt[1]}`).join(" ") +
    "Z";

  return (
    <svg width="180" height="180" viewBox="0 0 180 180">
      {[0.25, 0.5, 0.75, 1].map((l) => (
        <polygon
          key={l}
          points={pts(l)
            .map((p) => p.join(","))
            .join(" ")}
          fill="none"
          stroke="rgba(100,150,220,0.18)"
          strokeWidth="1"
        />
      ))}
      {skills.map((_, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={cx + r * Math.cos(angle)}
            y2={cy + r * Math.sin(angle)}
            stroke="rgba(100,150,220,0.2)"
            strokeWidth="1"
          />
        );
      })}
      <path
        d={toPath(
          pts(1).map((_, i) => {
            const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
            const d = r * skills[i].val;
            return [cx + d * Math.cos(angle), cy + d * Math.sin(angle)];
          })
        )}
        fill="rgba(80,140,220,0.18)"
        stroke="rgba(80,140,220,0.7)"
        strokeWidth="1.5"
      />
      {skills.map((s, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        const d = r * s.val;
        return (
          <circle
            key={i}
            cx={cx + d * Math.cos(angle)}
            cy={cy + d * Math.sin(angle)}
            r="3.5"
            fill="rgba(60,120,210,0.9)"
          />
        );
      })}
      {skills.map((s, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
        const lx = cx + (r + 16) * Math.cos(angle);
        const ly = cy + (r + 16) * Math.sin(angle);
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="9"
            fill="oklch(35% 0.1 240)"
            fontFamily="Plus Jakarta Sans"
          >
            {s.label}
          </text>
        );
      })}
    </svg>
  );
}

// ── HERO ─────────────────────────────────────────────────────────────────────
function Hero({ onCTAClick }: { onCTAClick: () => void }) {
  const [step, setStep] = useState(0);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    const sequence = [
      { step: 0, delay: 500 },
      { step: 1, delay: 4000 },
      { step: 2, delay: 7500 },
      { step: 3, delay: 11000 },
      { step: 4, delay: 14500 },
    ];
    const TOTAL = 20000;

    const run = () => {
      setStep(-1);
      sequence.forEach(({ step: s, delay }) => {
        timers.push(
          setTimeout(() => {
            setStep(s);
          }, delay)
        );
        timers.push(
          setTimeout(() => {
            if (chatRef.current) {
              chatRef.current.scrollTo({
                top: chatRef.current.scrollHeight,
                behavior: "smooth",
              });
            }
          }, delay + 500)
        );
      });
      timers.push(
        setTimeout(() => {
          if (chatRef.current)
            chatRef.current.scrollTo({ top: 0, behavior: "smooth" });
          setTimeout(run, 600);
        }, TOTAL)
      );
    };

    run();
    return () => timers.forEach(clearTimeout);
  }, []);

  const lines = HERO_HEADLINE.split("\n");

  return (
    <section
      style={{
        minHeight: "100svh",
        background: `radial-gradient(ellipse 80% 60% at 60% 0%, oklch(82% 0.08 ${ACCENT_HUE}) 0%, oklch(88% 0.05 ${ACCENT_HUE - 5}) 45%, oklch(92% 0.03 ${ACCENT_HUE + 10}) 100%)`,
        display: "flex",
        alignItems: "center",
        position: "relative",
        overflow: "hidden",
        paddingTop: 100,
      }}
    >
      <DotGrid opacity={0.14} />
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          padding: "0 40px",
          width: "100%",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 60,
          alignItems: "center",
        }}
      >
        {/* Left */}
        <div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "rgba(255,255,255,0.55)",
              backdropFilter: "blur(12px)",
              border: "1px solid rgba(255,255,255,0.85)",
              borderRadius: 50,
              padding: "6px 16px",
              marginBottom: 28,
              fontSize: 13,
              fontWeight: 500,
              color: `oklch(38% 0.14 ${ACCENT_HUE})`,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: `oklch(55% 0.18 ${ACCENT_HUE})`,
                display: "inline-block",
              }}
            ></span>
            AI-Powered English Coaching
          </div>
          <h1
            style={{
              fontSize: "clamp(38px, 4.5vw, 62px)",
              fontWeight: 800,
              lineHeight: 1.1,
              letterSpacing: "-1.5px",
              color: "oklch(15% 0.09 245)",
              marginBottom: 22,
            }}
          >
            {lines.map((l, i) => (
              <span key={i}>
                {l}
                {i < lines.length - 1 && <br />}
              </span>
            ))}
          </h1>
          <p
            style={{
              fontSize: 18,
              color: "oklch(38% 0.08 240)",
              lineHeight: 1.65,
              marginBottom: 36,
              maxWidth: 440,
              fontWeight: 400,
            }}
          >
            LingosAI is your strict, intelligent coach — diagnosing your real
            weaknesses, building personalized tasks, and giving precise feedback
            so you grow every single day.
          </p>
          <div
            style={{
              display: "flex",
              gap: 14,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <button
              onClick={onCTAClick}
              style={{
                padding: "15px 32px",
                borderRadius: 50,
                border: "none",
                cursor: "pointer",
                background: `oklch(20% 0.09 ${ACCENT_HUE})`,
                color: "white",
                fontFamily: "inherit",
                fontWeight: 700,
                fontSize: 16,
                boxShadow: "0 4px 24px rgba(20,50,120,0.22)",
                transition: "transform 0.15s, box-shadow 0.15s",
                letterSpacing: "-0.2px",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "scale(1.04)";
                e.currentTarget.style.boxShadow =
                  "0 6px 30px rgba(20,50,120,0.32)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "scale(1)";
                e.currentTarget.style.boxShadow =
                  "0 4px 24px rgba(20,50,120,0.22)";
              }}
            >
              {CTA_TEXT} →
            </button>
            <button
              style={{
                padding: "14px 28px",
                borderRadius: 50,
                border: "1.5px solid rgba(100,140,220,0.35)",
                background: "rgba(255,255,255,0.45)",
                backdropFilter: "blur(10px)",
                cursor: "pointer",
                fontFamily: "inherit",
                fontWeight: 600,
                fontSize: 15,
                color: `oklch(28% 0.1 ${ACCENT_HUE})`,
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "rgba(255,255,255,0.65)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "rgba(255,255,255,0.45)")
              }
            >
              ▶ See how it works
            </button>
          </div>
          <div
            style={{
              display: "flex",
              gap: 28,
              marginTop: 40,
              alignItems: "center",
            }}
          >
            {[
              ["12,000+", "Learners coached"],
              ["94%", "Improvement rate"],
              ["4.9★", "Average rating"],
            ].map(([val, label]) => (
              <div key={label}>
                <div
                  style={{
                    fontWeight: 800,
                    fontSize: 22,
                    color: "oklch(20% 0.09 245)",
                    letterSpacing: "-0.5px",
                  }}
                >
                  {val}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "oklch(45% 0.07 240)",
                    marginTop: 2,
                  }}
                >
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right — animated chat */}
        <div style={{ position: "relative" }}>
          <GlassCard style={{ padding: 14, maxWidth: 420, marginLeft: "auto" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 12,
                paddingBottom: 10,
                borderBottom: "1px solid rgba(180,200,240,0.3)",
              }}
            >
              <div
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 10,
                  background: "oklch(52% 0.18 240)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M2 13L8 3L14 13"
                    stroke="white"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M4.5 9.5h7"
                    stroke="white"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              </div>
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: "oklch(18% 0.09 245)",
                  }}
                >
                  Coach Lingos
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "oklch(52% 0.18 240)",
                    fontWeight: 500,
                  }}
                >
                  ● Online
                </div>
              </div>
              <div
                style={{
                  marginLeft: "auto",
                  background: "rgba(200,220,255,0.5)",
                  borderRadius: 50,
                  padding: "4px 10px",
                  fontSize: 11,
                  fontWeight: 600,
                  color: "oklch(38% 0.12 240)",
                }}
              >
                Daily Session
              </div>
            </div>
            <div
              ref={chatRef}
              className="landing-chat-scroll"
              style={{
                height: 320,
                overflowY: "scroll",
                display: "flex",
                flexDirection: "column",
                gap: 10,
                paddingRight: 4,
              }}
            >
              <ChatBubble role="ai" visible={step >= 0}>
                Your biggest gap is <strong>sentence structure</strong>. Let&apos;s
                work on it.
              </ChatBubble>
              <ChatBubble role="ai" visible={step >= 1}>
                <strong>Task:</strong> Describe your morning routine in 3
                sentences using present simple.
              </ChatBubble>
              <ChatBubble role="user" visible={step >= 2}>
                I wake up at 7am. Then I am going to gym. After that I take
                shower.
              </ChatBubble>
              <ChatBubble role="ai" visible={step >= 3}>
                Found <strong>2 grammar errors</strong> — see feedback below ↓
              </ChatBubble>
              {step >= 4 && (
                <div
                  style={{ opacity: 1, animation: "fadeSlideUp 0.6s ease forwards" }}
                >
                  <FeedbackCard />
                </div>
              )}
            </div>
            <div
              style={{
                marginTop: 10,
                display: "flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <div
                style={{
                  flex: 1,
                  background: "rgba(220,232,255,0.4)",
                  border: "1px solid rgba(180,210,255,0.5)",
                  borderRadius: 50,
                  padding: "9px 16px",
                  fontSize: 13,
                  color: "oklch(50% 0.08 240)",
                }}
              >
                Type your response…
              </div>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  background: "oklch(52% 0.18 240)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  flexShrink: 0,
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M2 7h10M8 3l4 4-4 4"
                    stroke="white"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
          </GlassCard>
        </div>
      </div>
    </section>
  );
}

// ── PROBLEM ──────────────────────────────────────────────────────────────────
function Problem() {
  const notList = [
    "Vocabulary drills & flashcards",
    "Gamified streaks with no real feedback",
    "Generic lessons not tailored to you",
    "Chatbots that just correct spelling",
  ];
  const yesList = [
    "Deep weakness diagnosis",
    "Personalized daily coaching tasks",
    "Precise, corrective AI feedback",
    "Career-focused communication training",
  ];
  return (
    <section
      style={{ padding: "100px 40px", background: "oklch(93% 0.025 240)" }}
    >
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 64 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
              color: "oklch(48% 0.14 240)",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            The Problem
          </div>
          <h2
            style={{
              fontSize: "clamp(30px, 3.5vw, 48px)",
              fontWeight: 800,
              letterSpacing: "-1px",
              color: "oklch(15% 0.09 245)",
              lineHeight: 1.15,
            }}
          >
            Most English apps keep you busy.
            <br />
            LingosAI makes you better.
          </h2>
        </div>
        <div
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}
        >
          <GlassCard style={{ padding: 36 }}>
            <div
              style={{
                fontWeight: 700,
                fontSize: 16,
                color: "oklch(45% 0.07 0)",
                marginBottom: 24,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span style={{ fontSize: 20 }}>✗</span> What you&apos;ve been doing
            </div>
            <div
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              {notList.map((t) => (
                <div
                  key={t}
                  style={{ display: "flex", gap: 12, alignItems: "center" }}
                >
                  <div
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: "rgba(220,80,80,0.1)",
                      border: "1.5px solid rgba(200,80,80,0.25)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 11,
                        color: "rgba(180,60,60,0.8)",
                        fontWeight: 700,
                      }}
                    >
                      ✕
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: 15,
                      color: "oklch(38% 0.07 240)",
                      lineHeight: 1.5,
                    }}
                  >
                    {t}
                  </span>
                </div>
              ))}
            </div>
          </GlassCard>
          <GlassCard
            style={{ padding: 36, background: "rgba(220,235,255,0.7)" }}
          >
            <div
              style={{
                fontWeight: 700,
                fontSize: 16,
                color: "oklch(30% 0.14 240)",
                marginBottom: 24,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span style={{ fontSize: 20 }}>✓</span> What LingosAI does
            </div>
            <div
              style={{ display: "flex", flexDirection: "column", gap: 14 }}
            >
              {yesList.map((t) => (
                <div
                  key={t}
                  style={{ display: "flex", gap: 12, alignItems: "center" }}
                >
                  <div
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: "rgba(60,140,220,0.15)",
                      border: "1.5px solid rgba(80,150,220,0.4)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 11,
                        color: "oklch(40% 0.18 240)",
                        fontWeight: 700,
                      }}
                    >
                      ✓
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: 15,
                      color: "oklch(28% 0.09 240)",
                      fontWeight: 500,
                      lineHeight: 1.5,
                    }}
                  >
                    {t}
                  </span>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </section>
  );
}

// ── HOW IT WORKS ─────────────────────────────────────────────────────────────
function HowItWorks() {
  const [active, setActive] = useState(0);
  const steps = [
    {
      n: "01",
      title: "AI Diagnoses You",
      desc: "Answer a few questions and do a short speaking + writing assessment. The AI maps your exact weakness profile across 6 skill dimensions.",
      icon: "◎",
    },
    {
      n: "02",
      title: "Get Your Daily Task",
      desc: "Every morning you receive a custom task targeting your weakest areas. It's not random — it's engineered to close your specific gaps.",
      icon: "◈",
    },
    {
      n: "03",
      title: "You Respond",
      desc: "Write or speak your response inside the app. The session feels like a real conversation with an expert coach, not a test.",
      icon: "◇",
    },
    {
      n: "04",
      title: "Receive Precise Feedback",
      desc: "AI highlights every error, explains why it is wrong, and gives you the corrected version with a rule explanation. No generic praise.",
      icon: "◉",
    },
  ];
  return (
    <section
      style={{
        padding: "100px 40px",
        background:
          "linear-gradient(160deg, oklch(88% 0.045 240) 0%, oklch(91% 0.03 250) 100%)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <DotGrid opacity={0.1} />
      <div
        style={{ maxWidth: 1180, margin: "0 auto", position: "relative" }}
      >
        <div style={{ textAlign: "center", marginBottom: 64 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
              color: "oklch(48% 0.14 240)",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            How It Works
          </div>
          <h2
            style={{
              fontSize: "clamp(30px, 3.5vw, 48px)",
              fontWeight: 800,
              letterSpacing: "-1px",
              color: "oklch(15% 0.09 245)",
              lineHeight: 1.15,
            }}
          >
            Task → Response → Feedback → Growth
          </h2>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 40,
            alignItems: "start",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {steps.map((s, i) => (
              <div
                key={i}
                onClick={() => setActive(i)}
                style={{
                  padding: "20px 24px",
                  borderRadius: 16,
                  cursor: "pointer",
                  background:
                    active === i
                      ? "rgba(255,255,255,0.78)"
                      : "rgba(255,255,255,0.35)",
                  border:
                    active === i
                      ? "1.5px solid rgba(255,255,255,0.9)"
                      : "1.5px solid rgba(255,255,255,0.5)",
                  boxShadow:
                    active === i
                      ? "0 4px 24px rgba(80,130,220,0.13)"
                      : "none",
                  transition: "all 0.2s",
                  backdropFilter: "blur(10px)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    gap: 16,
                    alignItems: "flex-start",
                  }}
                >
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      flexShrink: 0,
                      background:
                        active === i
                          ? "oklch(52% 0.18 240)"
                          : "rgba(180,210,255,0.4)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 800,
                      fontSize: 13,
                      color:
                        active === i ? "white" : "oklch(45% 0.1 240)",
                      transition: "all 0.2s",
                    }}
                  >
                    {s.n}
                  </div>
                  <div>
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 15,
                        color: "oklch(18% 0.09 245)",
                        marginBottom: 4,
                      }}
                    >
                      {s.title}
                    </div>
                    {active === i && (
                      <div
                        style={{
                          fontSize: 13.5,
                          color: "oklch(38% 0.07 240)",
                          lineHeight: 1.6,
                        }}
                      >
                        {s.desc}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <GlassCard style={{ padding: 28 }}>
            {active === 0 && (
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: "oklch(38% 0.1 240)",
                    marginBottom: 20,
                  }}
                >
                  Your Skill Profile
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "center",
                    marginBottom: 16,
                  }}
                >
                  <RadarChart
                    skills={[
                      { label: "Grammar", val: 0.45 },
                      { label: "Vocabulary", val: 0.62 },
                      { label: "Pronunciation", val: 0.38 },
                      { label: "Fluency", val: 0.58 },
                      { label: "Expression", val: 0.42 },
                      { label: "Comprehension", val: 0.7 },
                      { label: "Speech Delivery", val: 0.35 },
                    ]}
                  />
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 8,
                  }}
                >
                  {[
                    ["Grammar", "45%", "↑ Needs work"],
                    ["Pronunciation", "38%", "↑ Priority"],
                    ["Speech Delivery", "35%", "↑ Priority"],
                    ["Comprehension", "70%", "✓ Growing"],
                  ].map(([k, v, s]) => (
                    <div
                      key={k}
                      style={{
                        background: "rgba(210,225,255,0.4)",
                        borderRadius: 10,
                        padding: "10px 12px",
                      }}
                    >
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: 12,
                          color: "oklch(30% 0.1 240)",
                        }}
                      >
                        {k}
                      </div>
                      <div
                        style={{
                          fontWeight: 800,
                          fontSize: 18,
                          color: "oklch(22% 0.12 240)",
                        }}
                      >
                        {v}
                      </div>
                      <div
                        style={{ fontSize: 11, color: "oklch(48% 0.1 240)" }}
                      >
                        {s}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {active === 1 && (
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: "oklch(38% 0.1 240)",
                    marginBottom: 4,
                  }}
                >
                  Today&apos;s Task
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "oklch(50% 0.07 240)",
                    marginBottom: 20,
                  }}
                >
                  Targeting: Grammar · Sentence Structure
                </div>
                <div
                  style={{
                    background: "rgba(215,230,255,0.5)",
                    borderRadius: 14,
                    padding: 20,
                    marginBottom: 14,
                  }}
                >
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 13,
                      color: "oklch(28% 0.12 240)",
                      marginBottom: 8,
                    }}
                  >
                    📝 Writing Task — 5 min
                  </div>
                  <div
                    style={{
                      fontSize: 14,
                      color: "oklch(25% 0.08 240)",
                      lineHeight: 1.7,
                    }}
                  >
                    Imagine you are writing an email to your manager explaining
                    why you will be 30 minutes late today. Write 3–4 sentences
                    using the correct present continuous tense.
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {["Grammar", "Present Continuous", "Professional Writing"].map(
                    (t) => (
                      <span
                        key={t}
                        style={{
                          background: "rgba(190,215,255,0.55)",
                          borderRadius: 50,
                          padding: "4px 12px",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "oklch(35% 0.14 240)",
                        }}
                      >
                        {t}
                      </span>
                    )
                  )}
                </div>
              </div>
            )}
            {active === 2 && (
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: "oklch(38% 0.1 240)",
                    marginBottom: 20,
                  }}
                >
                  Live Session
                </div>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 10 }}
                >
                  <ChatBubble role="ai" visible>
                    Write 3 sentences about your morning routine using present
                    simple.
                  </ChatBubble>
                  <ChatBubble role="user" visible>
                    I wake up at 7. I am going to gym. I take shower before
                    work.
                  </ChatBubble>
                </div>
                <div
                  style={{
                    marginTop: 14,
                    background: "rgba(215,230,255,0.5)",
                    borderRadius: 12,
                    padding: "10px 14px",
                    fontSize: 13,
                    color: "oklch(40% 0.09 240)",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>Coach is analyzing…</span>{" "}
                  Checking grammar, tense usage, and sentence clarity.
                </div>
              </div>
            )}
            {active === 3 && <FeedbackCard />}
          </GlassCard>
        </div>
      </div>
    </section>
  );
}

// ── FEATURES ─────────────────────────────────────────────────────────────────
function Features() {
  const features = [
    {
      title: "Weakness Diagnosis",
      desc: "AI maps your exact skill gaps across all 7 subskills: Grammar, Vocabulary, Pronunciation, Fluency, Expression, Comprehension, and Speech Delivery.",
      icon: "◎",
      color: "230",
    },
    {
      title: "Personalized Daily Tasks",
      desc: "No two learners get the same task. Yours are built fresh each morning around your specific profile.",
      icon: "◈",
      color: "250",
    },
    {
      title: "Precise Feedback Engine",
      desc: "Every error is flagged, explained, and corrected with the underlying rule — not just a red underline.",
      icon: "◉",
      color: "210",
    },
    {
      title: "Multi-Skill Sessions",
      desc: "A single task simultaneously trains grammar, structure, vocabulary, and communication confidence.",
      icon: "◇",
      color: "270",
    },
    {
      title: "Progress Dashboard",
      desc: "See your skill radar evolve week by week. Hard numbers, not just streaks.",
      icon: "▣",
      color: "220",
    },
    {
      title: "Career-Focused Training",
      desc: "Practice job interviews, professional emails, and real meetings — not tourist phrases.",
      icon: "◆",
      color: "245",
    },
  ];
  return (
    <section
      style={{ padding: "100px 40px", background: "oklch(93% 0.022 240)" }}
    >
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 64 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
              color: "oklch(48% 0.14 240)",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            Features
          </div>
          <h2
            style={{
              fontSize: "clamp(30px, 3.5vw, 48px)",
              fontWeight: 800,
              letterSpacing: "-1px",
              color: "oklch(15% 0.09 245)",
              lineHeight: 1.15,
            }}
          >
            Everything a serious learner needs
          </h2>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 20,
          }}
        >
          {features.map((f, i) => (
            <GlassCard
              key={i}
              className="landing-feature-card"
              style={{
                padding: 28,
                transition: "transform 0.2s, box-shadow 0.2s",
                cursor: "default",
              }}
            >
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 13,
                  marginBottom: 18,
                  background: `oklch(82% 0.09 ${f.color})`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 22,
                  color: `oklch(38% 0.16 ${f.color})`,
                }}
              >
                {f.icon}
              </div>
              <div
                style={{
                  fontWeight: 700,
                  fontSize: 16,
                  color: "oklch(18% 0.09 245)",
                  marginBottom: 8,
                }}
              >
                {f.title}
              </div>
              <div
                style={{
                  fontSize: 14,
                  color: "oklch(42% 0.07 240)",
                  lineHeight: 1.65,
                }}
              >
                {f.desc}
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── UI PREVIEW ───────────────────────────────────────────────────────────────
function UIPreview() {
  const [tab, setTab] = useState("chat");
  const skills = [
    { label: "Grammar", val: 0.65 },
    { label: "Vocabulary", val: 0.78 },
    { label: "Pronunciation", val: 0.52 },
    { label: "Fluency", val: 0.72 },
    { label: "Expression", val: 0.68 },
    { label: "Comprehension", val: 0.82 },
    { label: "Speech Delivery", val: 0.58 },
  ];

  return (
    <section
      style={{
        padding: "100px 40px",
        background:
          "linear-gradient(180deg, oklch(88% 0.045 240) 0%, oklch(86% 0.055 238) 100%)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <DotGrid opacity={0.12} />
      <div
        style={{ maxWidth: 1180, margin: "0 auto", position: "relative" }}
      >
        <div style={{ textAlign: "center", marginBottom: 48 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
              color: "oklch(48% 0.14 240)",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            Product Preview
          </div>
          <h2
            style={{
              fontSize: "clamp(28px, 3vw, 44px)",
              fontWeight: 800,
              letterSpacing: "-1px",
              color: "oklch(15% 0.09 245)",
              lineHeight: 1.15,
            }}
          >
            Built like a professional coaching tool
          </h2>
        </div>
        <GlassCard style={{ padding: 6, overflow: "hidden" }}>
          <div
            style={{
              display: "flex",
              gap: 4,
              padding: "10px 14px 6px",
              borderBottom: "1px solid rgba(180,210,240,0.3)",
            }}
          >
            {[
              ["chat", "Coaching Session"],
              ["feedback", "Feedback View"],
              ["dashboard", "Progress Dashboard"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                style={{
                  padding: "7px 18px",
                  borderRadius: 50,
                  border: "none",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontWeight: 600,
                  fontSize: 13,
                  background:
                    tab === id ? "oklch(22% 0.09 245)" : "transparent",
                  color:
                    tab === id ? "white" : "oklch(45% 0.09 240)",
                  transition: "all 0.18s",
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div style={{ padding: 28 }}>
            {tab === "chat" && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "280px 1fr",
                  gap: 20,
                }}
              >
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 12 }}
                >
                  <GlassCard style={{ padding: 16 }}>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: "oklch(50% 0.1 240)",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                        marginBottom: 10,
                      }}
                    >
                      Today&apos;s Session
                    </div>
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 14,
                        color: "oklch(20% 0.1 245)",
                        marginBottom: 4,
                      }}
                    >
                      Professional Email Writing
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: "oklch(50% 0.08 240)",
                        marginBottom: 12,
                      }}
                    >
                      Targets: Grammar · Structure
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      {["Grammar", "Structure"].map((t) => (
                        <span
                          key={t}
                          style={{
                            background: "rgba(190,215,255,0.55)",
                            borderRadius: 50,
                            padding: "3px 10px",
                            fontSize: 10,
                            fontWeight: 600,
                            color: "oklch(35% 0.14 240)",
                          }}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </GlassCard>
                  <GlassCard style={{ padding: 16 }}>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: "oklch(50% 0.1 240)",
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                        marginBottom: 10,
                      }}
                    >
                      Skills This Week
                    </div>
                    {[
                      ["Grammar", 65],
                      ["Fluency", 72],
                      ["Pronunciation", 52],
                    ].map(([s, v]) => (
                      <div key={s} style={{ marginBottom: 10 }}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: 12,
                            fontWeight: 600,
                            color: "oklch(30% 0.09 240)",
                            marginBottom: 4,
                          }}
                        >
                          <span>{s}</span>
                          <span>{v}%</span>
                        </div>
                        <div
                          style={{
                            height: 5,
                            borderRadius: 10,
                            background: "rgba(180,210,240,0.4)",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              width: `${v}%`,
                              height: "100%",
                              borderRadius: 10,
                              background: "oklch(52% 0.18 240)",
                              transition: "width 0.5s",
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </GlassCard>
                </div>
                <GlassCard
                  style={{
                    padding: 20,
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                    minHeight: 360,
                  }}
                >
                  <ChatBubble role="ai" visible>
                    Good morning! Today&apos;s task focuses on professional email
                    writing. Ready?
                  </ChatBubble>
                  <ChatBubble role="ai" visible>
                    <strong>Task:</strong> Write a 3-sentence email to your
                    manager explaining you&apos;ll be working from home today due to
                    a doctor&apos;s appointment.
                  </ChatBubble>
                  <ChatBubble role="user" visible>
                    Hi [Manager], I am writing to inform you that I will working
                    from home today. I have a doctor appointment in morning. I
                    will ensure all my tasks are completed on time.
                  </ChatBubble>
                  <ChatBubble role="ai" visible>
                    Good structure! But I found <strong>3 errors</strong>. Check
                    the feedback panel for a full breakdown.
                  </ChatBubble>
                </GlassCard>
              </div>
            )}
            {tab === "feedback" && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 20,
                }}
              >
                <GlassCard style={{ padding: 22 }}>
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 14,
                      color: "oklch(38% 0.1 240)",
                      marginBottom: 16,
                    }}
                  >
                    Your Response
                  </div>
                  <p
                    style={{
                      fontSize: 14,
                      lineHeight: 1.9,
                      color: "oklch(22% 0.08 240)",
                    }}
                  >
                    Hi [Manager], I am writing to inform you that I will{" "}
                    <span
                      style={{
                        background: "rgba(220,60,60,0.12)",
                        borderBottom: "2px solid rgba(200,60,60,0.5)",
                        borderRadius: 2,
                      }}
                    >
                      working
                    </span>{" "}
                    from home today. I have a doctor{" "}
                    <span
                      style={{
                        background: "rgba(220,150,0,0.1)",
                        borderBottom: "2px solid rgba(200,130,0,0.4)",
                        borderRadius: 2,
                      }}
                    >
                      appointment
                    </span>{" "}
                    in{" "}
                    <span
                      style={{
                        background: "rgba(220,60,60,0.12)",
                        borderBottom: "2px solid rgba(200,60,60,0.5)",
                        borderRadius: 2,
                      }}
                    >
                      morning
                    </span>
                    . I will ensure all my tasks are completed on time.
                  </p>
                  <div
                    style={{ marginTop: 16, display: "flex", gap: 10 }}
                  >
                    <div
                      style={{
                        background: "rgba(220,80,80,0.12)",
                        borderRadius: 8,
                        padding: "6px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "oklch(40% 0.15 20)",
                      }}
                    >
                      2 Grammar Errors
                    </div>
                    <div
                      style={{
                        background: "rgba(220,150,0,0.1)",
                        borderRadius: 8,
                        padding: "6px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "oklch(40% 0.15 80)",
                      }}
                    >
                      1 Article Missing
                    </div>
                  </div>
                </GlassCard>
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 14 }}
                >
                  {[
                    {
                      err: '"will working"',
                      fix: '"will be working"',
                      rule: 'After "will", use the base verb or "will be + -ing" for future continuous.',
                      type: "Grammar",
                    },
                    {
                      err: '"in morning"',
                      fix: '"in the morning"',
                      rule: 'Use the definite article "the" before time expressions like "morning", "evening", "afternoon".',
                      type: "Article",
                    },
                  ].map((e, i) => (
                    <GlassCard key={i} style={{ padding: 18 }}>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: 11,
                          color: "oklch(48% 0.14 240)",
                          textTransform: "uppercase",
                          letterSpacing: 0.5,
                          marginBottom: 8,
                        }}
                      >
                        {e.type} Error
                      </div>
                      <div style={{ fontSize: 13, marginBottom: 8 }}>
                        <span
                          style={{
                            textDecoration: "line-through",
                            color: "oklch(50% 0.1 20)",
                          }}
                        >
                          {e.err}
                        </span>
                        {" → "}
                        <strong style={{ color: "oklch(35% 0.15 145)" }}>
                          {e.fix}
                        </strong>
                      </div>
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "oklch(38% 0.07 240)",
                          lineHeight: 1.6,
                          background: "rgba(215,230,255,0.5)",
                          borderRadius: 8,
                          padding: "8px 12px",
                        }}
                      >
                        {e.rule}
                      </div>
                    </GlassCard>
                  ))}
                </div>
              </div>
            )}
            {tab === "dashboard" && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 20,
                }}
              >
                <GlassCard
                  style={{ padding: 22, gridColumn: "span 1" } as React.CSSProperties}
                >
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 14,
                      color: "oklch(38% 0.1 240)",
                      marginBottom: 16,
                    }}
                  >
                    Skill Radar
                  </div>
                  <div style={{ display: "flex", justifyContent: "center" }}>
                    <RadarChart skills={skills} />
                  </div>
                </GlassCard>
                <GlassCard
                  style={{ padding: 22, gridColumn: "span 2" } as React.CSSProperties}
                >
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 14,
                      color: "oklch(38% 0.1 240)",
                      marginBottom: 20,
                    }}
                  >
                    Weekly Progress
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr 1fr",
                      gap: 12,
                      marginBottom: 20,
                    }}
                  >
                    {[
                      ["82", "Overall Score", "↑ +8 this week"],
                      ["14", "Sessions Done", "This month"],
                      ["94%", "Task completion", "Personal best"],
                    ].map(([v, l, s]) => (
                      <div
                        key={l}
                        style={{
                          background: "rgba(210,228,255,0.5)",
                          borderRadius: 12,
                          padding: 16,
                        }}
                      >
                        <div
                          style={{
                            fontWeight: 800,
                            fontSize: 28,
                            color: "oklch(22% 0.12 240)",
                            letterSpacing: "-1px",
                          }}
                        >
                          {v}
                        </div>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: 12,
                            color: "oklch(30% 0.09 240)",
                            marginBottom: 2,
                          }}
                        >
                          {l}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "oklch(50% 0.12 240)",
                          }}
                        >
                          {s}
                        </div>
                      </div>
                    ))}
                  </div>
                  {skills.map((s) => (
                    <div
                      key={s.label}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 12,
                        marginBottom: 10,
                      }}
                    >
                      <div
                        style={{
                          width: 100,
                          fontSize: 12,
                          fontWeight: 600,
                          color: "oklch(35% 0.09 240)",
                          flexShrink: 0,
                        }}
                      >
                        {s.label}
                      </div>
                      <div
                        style={{
                          flex: 1,
                          height: 7,
                          borderRadius: 10,
                          background: "rgba(180,210,240,0.4)",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${Math.round(s.val * 100)}%`,
                            height: "100%",
                            borderRadius: 10,
                            background: "oklch(52% 0.18 240)",
                          }}
                        />
                      </div>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: "oklch(28% 0.1 240)",
                          width: 32,
                          textAlign: "right",
                        }}
                      >
                        {Math.round(s.val * 100)}%
                      </div>
                    </div>
                  ))}
                </GlassCard>
              </div>
            )}
          </div>
        </GlassCard>
      </div>
    </section>
  );
}

// ── TESTIMONIALS ─────────────────────────────────────────────────────────────
function Testimonials() {
  const quotes = [
    {
      name: "Arjun S.",
      role: "Software Engineer, Bangalore",
      text: "I'd been using Duolingo for 2 years with no real improvement. After 3 weeks with LingosAI, my manager commented on how much clearer my communication had become.",
      initials: "AS",
    },
    {
      name: "Mei Lin C.",
      role: "MBA Student, Singapore",
      text: "The feedback is genuinely different. It doesn't just say 'wrong' — it tells me the exact rule I'm breaking and shows me a better sentence every time.",
      initials: "MC",
    },
    {
      name: "Rohan P.",
      role: "Product Manager, Mumbai",
      text: "I used to dread English presentations. After a month of daily coaching sessions, I gave a keynote to 200 people without notes. LingosAI is real.",
      initials: "RP",
    },
  ];
  return (
    <section
      style={{ padding: "100px 40px", background: "oklch(92% 0.028 240)" }}
    >
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              letterSpacing: 1,
              color: "oklch(48% 0.14 240)",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            Real Results
          </div>
          <h2
            style={{
              fontSize: "clamp(28px, 3vw, 44px)",
              fontWeight: 800,
              letterSpacing: "-1px",
              color: "oklch(15% 0.09 245)",
            }}
          >
            Built for serious learners
          </h2>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 20,
          }}
        >
          {quotes.map((q, i) => (
            <GlassCard key={i} style={{ padding: 28 }}>
              <div
                style={{
                  fontSize: 28,
                  color: "oklch(65% 0.14 240)",
                  marginBottom: 16,
                  lineHeight: 1,
                }}
              >
                &ldquo;
              </div>
              <p
                style={{
                  fontSize: 14.5,
                  color: "oklch(28% 0.07 240)",
                  lineHeight: 1.75,
                  marginBottom: 20,
                }}
              >
                {q.text}
              </p>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  paddingTop: 16,
                  borderTop: "1px solid rgba(180,210,240,0.35)",
                }}
              >
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background: "oklch(72% 0.1 240)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 13,
                    color: "oklch(25% 0.12 240)",
                  }}
                >
                  {q.initials}
                </div>
                <div>
                  <div
                    style={{
                      fontWeight: 700,
                      fontSize: 13.5,
                      color: "oklch(20% 0.09 245)",
                    }}
                  >
                    {q.name}
                  </div>
                  <div
                    style={{ fontSize: 12, color: "oklch(50% 0.07 240)" }}
                  >
                    {q.role}
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </section>
  );
}

// ── CTA ──────────────────────────────────────────────────────────────────────
function CTA({ onCTAClick }: { onCTAClick: () => void }) {
  return (
    <section
      style={{
        padding: "100px 40px",
        background: `linear-gradient(160deg, oklch(82% 0.07 ${ACCENT_HUE}) 0%, oklch(78% 0.09 ${ACCENT_HUE - 10}) 100%)`,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <DotGrid opacity={0.15} />
      <div
        style={{
          maxWidth: 700,
          margin: "0 auto",
          textAlign: "center",
          position: "relative",
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: 1,
            color: "rgba(255,255,255,0.7)",
            textTransform: "uppercase",
            marginBottom: 18,
          }}
        >
          Get Started Today
        </div>
        <h2
          style={{
            fontSize: "clamp(32px, 4vw, 56px)",
            fontWeight: 800,
            letterSpacing: "-1.5px",
            color: "oklch(14% 0.09 245)",
            lineHeight: 1.1,
            marginBottom: 20,
          }}
        >
          Start your English transformation today.
        </h2>
        <p
          style={{
            fontSize: 18,
            color: "oklch(28% 0.08 240)",
            lineHeight: 1.6,
            marginBottom: 40,
            maxWidth: 480,
            margin: "0 auto 40px",
          }}
        >
          Join 12,000+ learners getting daily personalized coaching. Your first
          week is free.
        </p>
        <div
          style={{
            display: "flex",
            gap: 14,
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <button
            onClick={onCTAClick}
            style={{
              padding: "17px 40px",
              borderRadius: 50,
              border: "none",
              cursor: "pointer",
              background: "oklch(18% 0.09 245)",
              color: "white",
              fontFamily: "inherit",
              fontWeight: 700,
              fontSize: 17,
              boxShadow: "0 6px 30px rgba(10,30,100,0.25)",
              transition: "transform 0.15s, box-shadow 0.15s",
              letterSpacing: "-0.3px",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = "scale(1.04)";
              e.currentTarget.style.boxShadow =
                "0 8px 36px rgba(10,30,100,0.35)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "scale(1)";
              e.currentTarget.style.boxShadow =
                "0 6px 30px rgba(10,30,100,0.25)";
            }}
          >
            {CTA_TEXT} — It&apos;s Free →
          </button>
        </div>
        <div
          style={{ marginTop: 24, fontSize: 13, color: "oklch(38% 0.07 240)" }}
        >
          No credit card required · Cancel anytime · 7-day free trial
        </div>
      </div>
    </section>
  );
}

// ── FOOTER ───────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer
      style={{
        padding: "48px 40px",
        background: "oklch(18% 0.09 245)",
        color: "rgba(255,255,255,0.55)",
      }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 8,
              background: "oklch(52% 0.18 240)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M2 11L7 3L12 11"
                stroke="white"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M4 8h6"
                stroke="white"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <span
            style={{
              fontWeight: 700,
              fontSize: 15,
              color: "rgba(255,255,255,0.85)",
            }}
          >
            LingosAI
          </span>
        </div>
        <div style={{ display: "flex", gap: 28, fontSize: 13 }}>
          {["Privacy", "Terms", "Contact", "Blog"].map((l) => (
            <a
              key={l}
              href="#"
              style={{ color: "rgba(255,255,255,0.5)", textDecoration: "none" }}
            >
              {l}
            </a>
          ))}
        </div>
        <div style={{ fontSize: 13 }}>© 2026 LingosAI. All rights reserved.</div>
      </div>
    </footer>
  );
}

// ── PAGE ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();

  const handleCTA = () => router.push("/login");

  return (
    <div
      style={{
        fontFamily: "'Plus Jakarta Sans', sans-serif",
        background: "#dde8f5",
        color: "oklch(18% 0.06 240)",
        minHeight: "100vh",
        overflowX: "hidden",
      }}
    >
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap"
      />
      <Nav onCTAClick={handleCTA} />
      <Hero onCTAClick={handleCTA} />
      <Problem />
      <HowItWorks />
      <Features />
      <UIPreview />
      <Testimonials />
      <CTA onCTAClick={handleCTA} />
      <Footer />
    </div>
  );
}
