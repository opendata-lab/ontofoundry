import type { ReactNode } from "react";

/**
 * Independent white header of a workspace page: a 16px title,
 * an optional 12px note beside it, and page actions aligned to the right edge.
 */
export function PageHeader({ title, note, breadcrumb, tabBar, children }: { title: ReactNode; note?: ReactNode; breadcrumb?: ReactNode; tabBar?: ReactNode; children?: ReactNode }) {
  // Ant Design's navigation styles require a div directly under the Tabs root.
  const Header = tabBar ? "div" : "header";
  return (
    <Header className="flex flex-none flex-col border-b border-rule bg-surface">
      <div className="flex min-h-page-header flex-col justify-center gap-2 px-4 py-2">
        {breadcrumb}
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="m-0 min-w-0 break-words text-base font-semibold text-ink">{title}</h1>
          {note && <span className="text-xs text-muted">{note}</span>}
          {children && <div className="ml-auto flex flex-wrap items-center gap-2">{children}</div>}
        </div>
      </div>
      {tabBar}
    </Header>
  );
}

/** Scrolling page body below the header, aligned to the same horizontal margin. */
export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex min-h-0 flex-1 flex-col gap-4 overflow-auto bg-canvas p-4 ${className}`.trim()}>{children}</div>;
}
