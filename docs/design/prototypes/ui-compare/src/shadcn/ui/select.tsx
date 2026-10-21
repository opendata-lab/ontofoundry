import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "./utils";

export interface Option { value: string; label: string; hint?: string }

/** Single select on Radix. An empty-string value is not allowed by Radix, so "none" stands for no value. */
export function Select({ value, onChange, options, placeholder, className, allowClear, clearLabel = "不选" }: {
  value: string | null; onChange: (v: string | null) => void; options: Option[]; placeholder?: string; className?: string; allowClear?: boolean; clearLabel?: string;
}) {
  return (
    <SelectPrimitive.Root value={value ?? (allowClear ? "__none" : undefined)} onValueChange={(v) => onChange(v === "__none" ? null : v)}>
      <SelectPrimitive.Trigger className={cn("flex h-9 w-full items-center justify-between gap-2 rounded-sm border border-rule bg-surface px-3 text-left text-sm outline-none focus:border-accent focus:ring-3 focus:ring-accent/15 data-[placeholder]:text-muted", className)}>
        <span className="truncate"><SelectPrimitive.Value placeholder={placeholder} /></span>
        <SelectPrimitive.Icon><ChevronDown size={15} className="text-muted" /></SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" sideOffset={4} className="z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border border-rule bg-surface shadow-lg">
          <SelectPrimitive.Viewport className="p-1">
            {allowClear && <Item value="__none" label={clearLabel} />}
            {options.map((o) => <Item key={o.value} {...o} />)}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

function Item({ value, label, hint }: Option) {
  return (
    <SelectPrimitive.Item value={value} className="relative flex cursor-default select-none flex-col rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none data-[highlighted]:bg-accent-soft">
      <SelectPrimitive.ItemText>{label}</SelectPrimitive.ItemText>
      {hint && <span className="text-xs text-muted">{hint}</span>}
      <SelectPrimitive.ItemIndicator className="absolute right-2 top-2"><Check size={14} className="text-accent" /></SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}
