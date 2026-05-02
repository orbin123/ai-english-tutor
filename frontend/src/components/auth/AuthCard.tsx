"use client";

import Link from "next/link";
import { ReactNode } from "react";

interface AuthCardProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

/**
 * Centered auth card on the soft-blue dotted gradient.
 * Matches the LingosAI landing-page glassmorphism / pill-button system.
 */
export function AuthCard({ title, subtitle, children, footer }: AuthCardProps) {
  return (
    <div
      className="relative min-h-screen w-full flex items-center justify-center px-4 py-12"
      style={{
        fontFamily: "'Plus Jakarta Sans', sans-serif",
        background:
          "radial-gradient(ellipse 80% 60% at 50% 0%, oklch(86% 0.07 240) 0%, oklch(90% 0.045 245) 50%, oklch(93% 0.025 250) 100%)",
      }}
    >
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap"
      />
      {/* Dotted pattern overlay */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(90,130,210,0.18) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }}
      />

      <div className="relative w-full max-w-[440px]">
        <div
          className="rounded-2xl bg-white/85 backdrop-blur-xl border border-white/90 px-8 py-10 sm:px-10 sm:py-12"
          style={{
            boxShadow:
              "0 4px 32px rgba(80,110,180,0.13), 0 1.5px 6px rgba(80,120,200,0.07)",
          }}
        >
          {/* Logo */}
          <Link
            href="/"
            className="inline-flex items-center gap-2 mb-8 group"
            aria-label="LingosAI home"
          >
            <div
              className="w-9 h-9 rounded-[10px] flex items-center justify-center transition-transform group-hover:scale-105"
              style={{ background: "oklch(52% 0.18 240)" }}
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path
                  d="M3.5 14L9 4L14.5 14"
                  stroke="white"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M5.7 10.5h6.6"
                  stroke="white"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                />
              </svg>
            </div>
            <span
              className="text-lg font-bold tracking-tight"
              style={{ color: "oklch(18% 0.09 245)", letterSpacing: "-0.02em" }}
            >
              LingosAI
            </span>
          </Link>

          {/* Title + subtitle */}
          <h1
            className="text-[26px] sm:text-[28px] font-extrabold leading-tight mb-2"
            style={{ color: "oklch(15% 0.09 245)", letterSpacing: "-0.02em" }}
          >
            {title}
          </h1>
          <p
            className="text-[15px] leading-relaxed mb-8"
            style={{ color: "oklch(45% 0.07 240)" }}
          >
            {subtitle}
          </p>

          {children}
        </div>

        {/* Footer (switch page link) */}
        <div
          className="mt-6 text-center text-sm"
          style={{ color: "oklch(40% 0.07 240)" }}
        >
          {footer}
        </div>
      </div>
    </div>
  );
}
