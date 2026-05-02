"use client";

export function SocialDivider() {
  return (
    <div className="my-6 flex items-center gap-3">
      <div
        className="flex-1 h-px"
        style={{ background: "oklch(88% 0.02 240)" }}
      />
      <span
        className="text-[12px] font-medium uppercase tracking-wider"
        style={{ color: "oklch(55% 0.06 240)" }}
      >
        Or continue with
      </span>
      <div
        className="flex-1 h-px"
        style={{ background: "oklch(88% 0.02 240)" }}
      />
    </div>
  );
}

export function GoogleButton() {
  return (
    <button
      type="button"
      className="w-full rounded-full py-3 text-[14.5px] font-semibold flex items-center justify-center gap-2.5 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
      style={{ color: "oklch(22% 0.09 245)" }}
    >
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
        <path
          fill="#4285F4"
          d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.79 2.71v2.26h2.9c1.7-1.57 2.69-3.88 2.69-6.61z"
        />
        <path
          fill="#34A853"
          d="M9 18c2.43 0 4.47-.81 5.96-2.18l-2.9-2.26c-.8.54-1.83.86-3.06.86-2.35 0-4.34-1.59-5.05-3.72H.96v2.33A9 9 0 0 0 9 18z"
        />
        <path
          fill="#FBBC05"
          d="M3.95 10.7A5.41 5.41 0 0 1 3.66 9c0-.59.1-1.16.29-1.7V4.97H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.03l2.99-2.33z"
        />
        <path
          fill="#EA4335"
          d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 9 0 9 9 0 0 0 .96 4.97L3.95 7.3C4.66 5.17 6.65 3.58 9 3.58z"
        />
      </svg>
      Continue with Google
    </button>
  );
}
