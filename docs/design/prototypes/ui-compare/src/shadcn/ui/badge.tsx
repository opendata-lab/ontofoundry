import type { ComponentProps } from "react";
import { cn } from "./utils";

export const Badge = ({ className, ...p }: ComponentProps<"span">) => (
  <span className={cn("inline-flex items-center gap-1 rounded-sm border border-rule bg-surface-soft px-1.5 py-0.5 text-xs text-ink-2", className)} {...p} />
);
