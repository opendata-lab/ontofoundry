/** Sidebar link look shared by the workspace and account navigation. */
export function navLinkClass(isActive: boolean) {
  return `app-nav-link flex min-h-10 items-center gap-3 rounded-sm px-3 text-sm ${isActive ? "bg-accent-soft font-semibold text-accent hover:text-accent" : "text-ink-2 hover:bg-surface-soft hover:text-ink"}`;
}
