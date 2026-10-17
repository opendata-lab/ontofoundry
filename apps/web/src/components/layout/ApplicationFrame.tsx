import type { ReactNode } from "react";

/** Shared chrome; the main region leaves scrolling to each retained page. */
export function ApplicationFrame({
  header,
  sidebar,
  collapsed,
  children,
}: {
  header: ReactNode;
  sidebar: ReactNode;
  collapsed: boolean;
  children: ReactNode;
}) {
  return (
    <div className="app-shell" data-collapsed={collapsed}>
      <header className="col-span-full flex items-center justify-between border-b border-rule-soft bg-surface px-5">
        {header}
      </header>
      <aside className="app-sidebar flex min-h-0 flex-col border-r border-rule-soft bg-surface pt-5 pb-3">
        {sidebar}
      </aside>
      <main className="min-h-0 min-w-0 overflow-hidden">{children}</main>
    </div>
  );
}
