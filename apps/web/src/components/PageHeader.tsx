import type { ReactNode } from "react";

/**
 * Top header row of a workspace page on the canvas background: a 16px title,
 * an optional 12px note beside it, and page actions aligned to the right edge.
 */
export function PageHeader({ title, note, children }: { title: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-none flex-wrap items-center gap-3 px-6 pt-5 pb-3">
      <h1 className="m-0 text-base font-semibold whitespace-nowrap text-ink">{title}</h1>
      {note && <span className="text-xs text-muted">{note}</span>}
      {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

/** Scrolling page body below the header, aligned to the same horizontal margin. */
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-6 pb-6 pt-0 ${className}`.trim()}>{children}</div>;
}
