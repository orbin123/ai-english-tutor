"use client";

interface ServerErrorBannerProps {
  message?: string | null;
}

export function ServerErrorBanner({ message }: ServerErrorBannerProps) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 flex items-start gap-2.5"
    >
      <svg
        className="w-4 h-4 mt-0.5 flex-shrink-0 text-red-500"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden
      >
        <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M8 5v3.5M8 11v.01"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <p className="text-[13.5px] font-medium leading-snug text-red-700">
        {message}
      </p>
    </div>
  );
}
