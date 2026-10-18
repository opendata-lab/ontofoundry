import type { ReactNode } from "react";

/**
 * Compact section heading row with an optional note and right-aligned actions.
 */
export function SectionTitle({
  title,
  note,
  children,
  className = "",
}: {
  title: ReactNode;
  note?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`.trim()}>
      <h2 className="m-0 text-sm font-semibold text-ink">{title}</h2>
      {note && <span className="text-xs text-muted">{note}</span>}
      {children && <div className="ml-auto flex items-center gap-2">{children}</div>}
    </div>
  );
}
