import * as Popover from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useState } from "react";
import type { Option } from "./select";
import { cn } from "./utils";

/** Searchable single select: Radix popover + cmdk, the shadcn/ui Combobox pattern. */
export function Combobox({ value, onChange, options, placeholder, searchPlaceholder }: {
  value: string | null; onChange: (v: string) => void; options: Option[]; placeholder?: string; searchPlaceholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger className="flex h-9 w-full items-center justify-between rounded-sm border border-rule bg-surface px-3 text-left text-sm outline-none focus:border-accent focus:ring-3 focus:ring-accent/15">
        <span className={cn("truncate", !current && "text-muted")}>{current?.label ?? placeholder}</span>
        <ChevronsUpDown size={15} className="text-muted" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={4} align="start" className="z-50 w-[var(--radix-popover-trigger-width)] rounded-md border border-rule bg-surface shadow-lg">
          <Command>
            <div className="flex items-center gap-2 border-b border-rule-soft px-3">
              <Search size={14} className="text-muted" />
              <Command.Input placeholder={searchPlaceholder} className="h-9 w-full bg-transparent text-sm outline-none" />
            </div>
            <Command.List className="max-h-64 overflow-auto p-1">
              <Command.Empty className="py-6 text-center text-sm text-muted">没有匹配的数据集</Command.Empty>
              {options.map((o) => (
                <Command.Item key={o.value} value={`${o.label} ${o.hint ?? ""}`} onSelect={() => { onChange(o.value); setOpen(false); }}
                  className="relative flex cursor-default flex-col rounded-sm py-1.5 pl-2 pr-8 text-sm data-[selected=true]:bg-accent-soft">
                  <span>{o.label}</span>
                  {o.hint && <span className="text-xs text-muted">{o.hint}</span>}
                  {o.value === value && <Check size={14} className="absolute right-2 top-2 text-accent" />}
                </Command.Item>
              ))}
            </Command.List>
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
