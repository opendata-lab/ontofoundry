import type { ComponentProps } from "react";
import { cn } from "./utils";

const field = "w-full rounded-sm border border-rule bg-surface px-3 text-sm text-ink placeholder:text-muted/70 outline-none transition focus:border-accent focus:ring-3 focus:ring-accent/15 disabled:bg-surface-soft disabled:text-muted";

export const Input = ({ className, ...p }: ComponentProps<"input">) => <input className={cn(field, "h-9", className)} {...p} />;
export const Textarea = ({ className, ...p }: ComponentProps<"textarea">) => <textarea className={cn(field, "py-2 leading-6", className)} {...p} />;
