import type { ReactNode } from "react";

/**
 * Primary white container panel on the canvas background. Keeps toolbars,
 * tables, and optional footer notes inside a single white surface so a
 * page never exceeds the "canvas -> panel" two-layer container hierarchy.
 */
export function Panel({
  children,
  footer,
  fill = false,
  className = "",
}: {
  children: ReactNode;
  footer?: ReactNode;
  /** Workbench panels fill the available height and scroll their own content. */
  fill?: boolean;
  className?: string;
}) {
  return (
    <section
      className={`flex ${fill ? "min-h-0 flex-1" : "flex-none"} flex-col overflow-hidden rounded-xs bg-surface shadow-panel ${className}`.trim()}
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
