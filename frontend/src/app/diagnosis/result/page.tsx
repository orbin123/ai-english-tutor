"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useDiagnosisStore } from "@/store/diagnosisStore";

const SKILL_LABELS: Record<string, string> = {
  grammar: "Grammar",
  vocabulary: "Vocabulary",
  pronunciation: "Pronunciation",
  fluency: "Fluency",
  expression: "Expression",
  tone: "Tone",
  comprehension: "Comprehension",
};

// Diagnosis scores are capped at 4 (out of a real 0-10 scale).
// Multiply by 2.5 to display on 0-10 scale.
function toDisplayScore(diagnosisScore: number): number {
  return parseFloat((diagnosisScore * 2.5).toFixed(1));
}

function displayScoreColor(displayScore: number): string {
  if (displayScore >= 8) return "bg-emerald-500";
  if (displayScore >= 6) return "bg-blue-500";
  if (displayScore >= 4) return "bg-amber-400";
  return "bg-red-400";
}

function displayScoreLabel(displayScore: number): string {
  if (displayScore >= 8) return "Strong";
  if (displayScore >= 6) return "Developing";
  if (displayScore >= 4) return "Needs work";
  return "Weak";
}

function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          entry.target.classList.remove("opacity-40", "blur-[4px]");
          entry.target.classList.add("opacity-100", "blur-none");
          observer.unobserve(entry.target);
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px -50px 0px" }
    );
    
    if (ref.current) {
      observer.observe(ref.current);
    }
    
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`opacity-40 blur-[4px] transition-all duration-[600ms] ease-out ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

export default function DiagnosisResultPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { result, clear } = useDiagnosisStore();

  useEffect(() => {
    if (!result) router.replace("/diagnosis");
  }, [result, router]);

  if (!result) return null;

  const { skill_scores, weakest_skills, feedback } = result;

  const continueToDashboard = () => {
    // NOW we invalidate /me — after the user has seen the result.
    queryClient.invalidateQueries({ queryKey: ["me"] });
    clear();
    router.push("/dashboard");
  };

  return (
    <main
      className="relative min-h-screen w-full bg-gradient-to-b from-[#dbeafe] to-[#eff6ff] pb-24"
      style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
    >
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap"
      />
      
      <style>{`
        @keyframes slideDownFade {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-slide-down-fade {
          animation: slideDownFade 400ms ease-out forwards;
        }
        
        @keyframes subtlePulse {
          0% { transform: scale(1); box-shadow: 0 4px 18px rgba(10,15,31,0.25); }
          50% { transform: scale(1.02); box-shadow: 0 8px 24px rgba(10,15,31,0.35); }
          100% { transform: scale(1); box-shadow: 0 4px 18px rgba(10,15,31,0.25); }
        }
        .animate-subtle-pulse {
          animation: subtlePulse 2s ease-in-out 2;
        }
      `}</style>

      {/* Dot pattern */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(37,99,235,0.10) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }}
      />

      <section className="relative z-10 mx-auto w-full max-w-5xl px-4 py-12 sm:px-6">
        {/* Header */}
        <div className="mb-12 text-center animate-slide-down-fade opacity-0">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-white px-3 py-1 text-[12.5px] font-semibold text-blue-800 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
            Diagnosis complete
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-[#0a1f44] sm:text-[36px]">
            Your starting profile
          </h1>
          <p className="mt-3 text-[15.5px] text-slate-600">
            Here is an honest picture of where you are right now.
          </p>
        </div>

        <div className="flex flex-col gap-8 md:flex-row">
          {/* Left Column (40%) - Sticky */}
          <div className="flex-shrink-0 md:w-[40%]">
            <div className="sticky top-8 space-y-6">
              <Reveal>
                <div className="rounded-3xl border border-white/90 bg-white/90 px-6 py-7 shadow-[0_8px_32px_rgba(15,23,42,0.06)] backdrop-blur-xl">
                  <div className="flex items-center gap-3">
                    <span className="rounded-full bg-blue-600 px-4 py-1.5 text-[13px] font-bold text-white shadow-sm">
                      {feedback.estimated_level_label}
                    </span>
                  </div>
                  <p className="mt-5 text-[15px] leading-relaxed text-[#0a1f44]">
                    {feedback.summary}
                  </p>
                </div>
              </Reveal>

              <Reveal delay={150}>
                <div className="rounded-3xl border border-blue-100 bg-blue-50/80 px-6 py-6 shadow-[0_4px_16px_rgba(37,99,235,0.08)] backdrop-blur-sm">
                  <p className="text-[15px] font-semibold leading-relaxed text-blue-900">
                    {feedback.motivation}
                  </p>
                  <p className="mt-3 text-[13.5px] leading-relaxed text-blue-800">
                    <span className="font-semibold">First week focus: </span>
                    {feedback.first_week_focus}
                  </p>
                </div>
              </Reveal>
            </div>
          </div>

          {/* Right Column (60%) - Scrollable content */}
          <div className="space-y-8 md:w-[60%]">
            {/* Skill scores */}
            <Reveal>
              <div className="rounded-3xl border border-white/90 bg-white/90 px-6 py-7 shadow-[0_8px_32px_rgba(15,23,42,0.06)] backdrop-blur-xl">
                <h2 className="mb-6 text-[13px] font-bold uppercase tracking-widest text-slate-500">
                  Detailed Skill Scores
                </h2>
                <ul className="space-y-10">
                  {Object.entries(skill_scores)
                    .sort((a, b) => a[1] - b[1])
                    .map(([key, score]) => {
                      const displayScore = toDisplayScore(score);
                      const isWeak = weakest_skills.includes(key);
                      return (
                        <li key={key} className="relative">
                          <div className="mb-2 flex items-center justify-between text-[13.5px]">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-[#0a1f44]">
                                {SKILL_LABELS[key] ?? key}
                              </span>
                              {isWeak && (
                                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 border border-amber-100">
                                  Focus area
                                </span>
                              )}
                            </div>
                            <span className="font-medium text-slate-500">
                              {displayScore.toFixed(1)} / 10 &middot; {displayScoreLabel(displayScore)}
                            </span>
                          </div>
                          
                          <div className="relative mt-2 h-2 w-full rounded-full bg-slate-100">
                            {/* The filled bar */}
                            <div
                              className={`absolute left-0 top-0 h-full rounded-full transition-all duration-[1000ms] ease-out ${displayScoreColor(displayScore)}`}
                              style={{ width: `${(displayScore / 10) * 100}%` }}
                            />
                            

                          </div>
                        </li>
                      );
                    })}
                </ul>
              </div>
            </Reveal>

            {/* Weak skill explanations */}
            {feedback.weak_skill_explanations.length > 0 && (
              <div className="space-y-4">
                <Reveal>
                  <h2 className="ml-2 mt-4 text-[13px] font-bold uppercase tracking-widest text-slate-500">
                    We will focus on
                  </h2>
                </Reveal>
                
                {feedback.weak_skill_explanations.map((exp, index) => (
                  <Reveal key={exp.skill_name} delay={index * 100}>
                    <div className="rounded-2xl border border-white/90 border-l-[4px] border-l-amber-400 bg-white/90 p-6 shadow-[0_8px_32px_rgba(15,23,42,0.06)] backdrop-blur-xl">
                      <div className="mb-4">
                        <span className="inline-block rounded-full bg-amber-50 px-3 py-1 text-[13px] font-bold text-amber-800">
                          {SKILL_LABELS[exp.skill_name] ?? exp.skill_name}
                        </span>
                      </div>
                      <div className="space-y-4">
                        <div>
                          <p className="text-[12px] font-bold uppercase tracking-wider text-slate-400">
                            What it is
                          </p>
                          <p className="mt-1 text-[14.5px] leading-relaxed text-[#0a1f44]">
                            {exp.what_it_means}
                          </p>
                        </div>
                        <div>
                          <p className="text-[12px] font-bold uppercase tracking-wider text-slate-400">
                            Why it matters
                          </p>
                          <p className="mt-1 text-[14.5px] leading-relaxed text-[#0a1f44]">
                            {exp.why_it_matters}
                          </p>
                        </div>
                        <div>
                          <p className="text-[12px] font-bold uppercase tracking-wider text-slate-400">
                            What you will practice
                          </p>
                          <p className="mt-1 text-[14.5px] leading-relaxed text-slate-600">
                            {exp.what_to_expect}
                          </p>
                        </div>
                      </div>
                    </div>
                  </Reveal>
                ))}
              </div>
            )}

            {/* CTA */}
            <Reveal delay={200}>
              <div className="pt-6">
                <button
                  onClick={continueToDashboard}
                  className="animate-subtle-pulse w-full rounded-full bg-[#0a0f1f] py-4 text-[16px] font-bold text-white shadow-[0_4px_18px_rgba(10,15,31,0.25)] transition-all hover:scale-[1.01] active:scale-[0.99]"
                >
                  Start my journey →
                </button>
              </div>
            </Reveal>
          </div>
        </div>
      </section>
    </main>
  );
}
