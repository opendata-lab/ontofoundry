import { createContext, useContext, useLayoutEffect } from "react";

export type PageTabMeta = { title?: string; dirty?: boolean; busy?: boolean };
export const PageTabContext = createContext<{
  active: boolean;
  update: (meta: PageTabMeta) => void;
} | null>(null);

export function usePageActive() {
  return useContext(PageTabContext)?.active ?? true;
}

export function usePageTab({
  title,
  dirty = false,
  busy = false,
}: PageTabMeta) {
  const update = useContext(PageTabContext)?.update;
  useLayoutEffect(() => {
    update?.({ title, dirty, busy });
  }, [update, title, dirty, busy]);
}
