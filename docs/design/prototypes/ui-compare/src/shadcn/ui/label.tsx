import * as LabelPrimitive from "@radix-ui/react-label";
import type { ComponentProps } from "react";
import { cn } from "./utils";

export const Label = ({ className, ...p }: ComponentProps<typeof LabelPrimitive.Root>) => (
  <LabelPrimitive.Root className={cn("text-sm font-medium text-ink-2", className)} {...p} />
);

export function Field({ label, hint, required, children, className }: { label: string; hint?: React.ReactNode; required?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label>{label}{required && <span className="ml-0.5 text-danger">*</span>}</Label>
      {children}
      {hint && <p className="text-xs leading-5 text-muted">{hint}</p>}
    </div>
  );
}
