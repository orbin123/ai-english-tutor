"use client";

import { forwardRef, InputHTMLAttributes } from "react";

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
  rightSlot?: React.ReactNode;
}

export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(
  function FormField({ label, error, hint, rightSlot, id, ...rest }, ref) {
    const fieldId =
      id || `field-${label.toLowerCase().replace(/\s+/g, "-")}`;

    return (
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <label
            htmlFor={fieldId}
            className="text-[13px] font-semibold"
            style={{ color: "oklch(25% 0.08 245)" }}
          >
            {label}
          </label>
          {rightSlot}
        </div>

        <input
          ref={ref}
          id={fieldId}
          aria-invalid={!!error}
          aria-describedby={
            error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined
          }
          className={[
            "w-full rounded-lg px-3.5 py-2.5 text-[14.5px] bg-white",
            "transition-all outline-none",
            "placeholder:text-slate-400",
            error
              ? "border-2 border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-200"
              : "border border-slate-200 focus:border-blue-500 focus:ring-2 focus:ring-blue-200/60",
          ].join(" ")}
          style={{ color: "oklch(18% 0.09 245)" }}
          {...rest}
        />

        {error ? (
          <p
            id={`${fieldId}-error`}
            className="mt-1.5 text-[12.5px] font-medium text-red-600"
          >
            {error}
          </p>
        ) : hint ? (
          <p
            id={`${fieldId}-hint`}
            className="mt-1.5 text-[12.5px]"
            style={{ color: "oklch(50% 0.06 240)" }}
          >
            {hint}
          </p>
        ) : null}
      </div>
    );
  }
);
