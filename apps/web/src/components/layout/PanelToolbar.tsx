import type { ReactNode } from "react";

/**
 * Horizontal toolbar at the top of a Panel. Aligns tabs or left-hand controls
 * with right-hand filters and search inputs in a single compact row whose
 * horizontal padding matches the table cell padding below it.
 */
export function PanelToolbar({
  children,
  extra,
  className = "",
}: {
  children?: ReactNode;
  extra?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex min-h-10 flex-wrap items-center justify-between gap-3 border-b border-rule px-4 ${className}`.trim()}
    >
      {children && <div className="flex min-w-0 items-center gap-3">{children}</div>}
      {extra && <div className="ml-auto flex flex-wrap items-center gap-2 py-1">{extra}</div>}
    </div>
  );
}
