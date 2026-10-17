import type { ReactNode } from "react";

/**
 * Primary white container panel on the canvas background. Keeps toolbars,
 * tables, and optional footer notes inside a single bordered surface so a
 * page never exceeds the "canvas -> panel" two-layer container hierarchy.
 */
export function Panel({
  children,
  footer,
  className = "",
}: {
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`flex flex-none flex-col overflow-hidden rounded-md border border-rule bg-surface shadow-panel ${className}`.trim()}
    >
      {children}
      {footer && (
        <footer className="border-t border-rule bg-surface-raised px-4 py-2 text-xs text-muted">
          {footer}
        </footer>
      )}
    </section>
  );
}
