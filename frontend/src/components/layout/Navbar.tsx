"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { UserOut } from "@/lib/auth-api";

interface NavbarProps {
  user: UserOut | undefined;
}

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/stats", label: "Stats" },
  { href: "/profile", label: "Profile" },
  { href: "/settings", label: "Settings" },
] as const;

function getInitials(name: string | undefined): string {
  if (!name) return "??";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function Navbar({ user }: NavbarProps) {
  const pathname = usePathname();

  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        background: "rgba(255,255,255,0.8)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid rgba(80,120,200,0.12)",
        animation: "slideDown 0.3s ease both",
        fontFamily: "'Plus Jakarta Sans', sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: 1180,
          margin: "0 auto",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: 64,
          padding: "0 24px",
        }}
      >
        {/* Left — Logo */}
        <Link
          href="/dashboard"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            textDecoration: "none",
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "oklch(52% 0.18 240)",
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
              color: "oklch(18% 0.09 245)",
              letterSpacing: "-0.3px",
            }}
          >
            LingosAI
          </span>
        </Link>

        {/* Center — Nav links */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {NAV_LINKS.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                style={{
                  position: "relative",
                  padding: "6px 14px",
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 500,
                  color: isActive
                    ? "oklch(52% 0.18 240)"
                    : "oklch(45% 0.07 240)",
                  background: isActive
                    ? "oklch(93% 0.025 250)"
                    : "transparent",
                  textDecoration: "none",
                  transition:
                    "background 0.15s ease, color 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background =
                      "oklch(95% 0.015 250)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isActive) {
                    e.currentTarget.style.background = "transparent";
                  }
                }}
              >
                {link.label}
                {isActive && (
                  <span
                    style={{
                      position: "absolute",
                      bottom: -1,
                      left: "50%",
                      transform: "translateX(-50%)",
                      width: 20,
                      height: 2,
                      borderRadius: 1,
                      background: "oklch(52% 0.18 240)",
                    }}
                  />
                )}
              </Link>
            );
          })}
        </div>

        {/* Right — Avatar */}
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "oklch(52% 0.18 240)",
            color: "white",
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: "0.5px",
            flexShrink: 0,
          }}
        >
          {getInitials(user?.name)}
        </div>
      </div>
    </nav>
  );
}
