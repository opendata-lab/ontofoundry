import type { ReactNode } from "react";

/** Page actions and filters sit on the canvas, outside the list surface. */
export function PageToolbar({ children, extra }: { children?: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex flex-none flex-wrap items-center justify-between gap-3">
      {children && <div className="flex min-w-0 flex-wrap items-center gap-2">{children}</div>}
      {extra && <div className="ml-auto flex min-w-0 flex-wrap items-center gap-3">{extra}</div>}
    </div>
  );
}
