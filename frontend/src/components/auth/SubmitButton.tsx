"use client";

import { ButtonHTMLAttributes } from "react";

interface SubmitButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  loadingText?: string;
}

export function SubmitButton({
  loading = false,
  loadingText,
  children,
  disabled,
  className = "",
  ...rest
}: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={disabled || loading}
      className={[
        "w-full rounded-full py-3 text-[15px] font-bold tracking-tight",
        "text-white transition-all",
        "flex items-center justify-center gap-2",
        "disabled:opacity-70 disabled:cursor-not-allowed",
        "hover:enabled:scale-[1.01] active:enabled:scale-[0.99]",
        className,
      ].join(" ")}
      style={{
        background: "oklch(20% 0.09 245)",
        boxShadow: "0 4px 18px rgba(20,50,120,0.22)",
      }}
      {...rest}
    >
      {loading && (
        <svg
          className="animate-spin h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden
        >
          <circle
            cx="12"
            cy="12"
            r="9"
            stroke="white"
            strokeOpacity="0.3"
            strokeWidth="3"
          />
          <path
            d="M21 12a9 9 0 0 0-9-9"
            stroke="white"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
      )}
      <span>{loading ? loadingText ?? "Loading..." : children}</span>
    </button>
  );
}
