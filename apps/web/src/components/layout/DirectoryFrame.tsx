import type { ReactNode } from "react";

/** Standalone directory chrome, sharing page margins with workspace pages. */
export function DirectoryFrame({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="flex h-app-header flex-none items-center justify-between border-b border-rule-soft bg-surface px-6">
        {header}
      </header>
      <main className="mx-auto flex w-full max-w-directory flex-1 flex-col">{children}</main>
    </div>
  );
}
