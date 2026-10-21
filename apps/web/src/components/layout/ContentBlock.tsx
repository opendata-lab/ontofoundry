import { useContext, type ComponentPropsWithRef, type ReactNode } from "react";
import { SeparateBlocks } from "./contentBlockContext";

/** Independent detail pages provide surfaces; dialogs already own their frame. */
export function ContentBlockScope({ children, separate }: { children: ReactNode; separate: boolean }) {
  return <SeparateBlocks.Provider value={separate}>{children}</SeparateBlocks.Provider>;
}

/** A business section; nested sections stay flat within their owning block. */
export function ContentBlock({ children, className = "", ...props }: ComponentPropsWithRef<"section">) {
  const separate = useContext(SeparateBlocks);
  return (
    <section {...props} className={`flex min-w-0 flex-col gap-3 ${separate ? "rounded-xs bg-surface p-4 shadow-panel" : ""} ${className}`.trim()}>
      <SeparateBlocks.Provider value={false}>{children}</SeparateBlocks.Provider>
    </section>
  );
}
