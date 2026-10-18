import type { ReactNode } from "react";

/**
 * The white band at the top of every workspace page: a compact title, an
 * optional note beside it and the page actions on the right.
 */
export function PageHeader({ title, note, children }: { title: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex min-h-14 flex-none flex-wrap items-center gap-3 border-b border-rule-soft bg-surface px-5 py-2">
      <h1 className="m-0 text-sm font-semibold whitespace-nowrap text-ink">{title}</h1>
      {note && <span className="text-xs text-muted">{note}</span>}
      {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  );
}

/** Scrolling page body below the header. */
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-5 py-4 ${className}`}>{children}</div>;
}
