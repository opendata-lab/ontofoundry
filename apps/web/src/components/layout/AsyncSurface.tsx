import type { ComponentProps } from "react";

/** Consistent spacing for async feedback, with no extra panel layer. */
export function AsyncSurface({ fullPage = false, className = "", ...props }: ComponentProps<"div"> & { fullPage?: boolean }) {
  return (
    <div
      className={`${fullPage ? "flex min-h-dvh items-center justify-center bg-canvas " : ""}p-6 ${className}`.trim()}
      {...props}
    />
  );
}
