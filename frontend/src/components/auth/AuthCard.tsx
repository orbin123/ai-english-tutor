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

      {/* Top Navigation Bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 px-10">
        <div className="max-w-[1180px] mx-auto flex items-center h-[68px]">
          <Link
            href="/"
            className="flex items-center gap-2 group"
            aria-label="LingosAI home"
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-transform group-hover:scale-105"
              style={{ background: "oklch(52% 0.18 240)" }}
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
              className="font-bold text-[17px] tracking-tight"
              style={{ color: "oklch(18% 0.09 245)", letterSpacing: "-0.3px" }}
            >
              LingosAI
            </span>
          </Link>
        </div>
      </nav>

      <div className="relative w-full max-w-[440px]">
        <div
          className="rounded-2xl bg-white/85 backdrop-blur-xl border border-white/90 px-8 py-10 sm:px-10 sm:py-12"
          style={{
            boxShadow:
              "0 4px 32px rgba(80,110,180,0.13), 0 1.5px 6px rgba(80,120,200,0.07)",
          }}
        >

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
