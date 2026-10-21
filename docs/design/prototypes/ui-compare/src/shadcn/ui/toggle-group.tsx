import * as ToggleGroup from "@radix-ui/react-toggle-group";

export function Segmented({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <ToggleGroup.Root type="single" value={value} onValueChange={(v) => v && onChange(v)}
      className="inline-flex flex-wrap gap-1 rounded-md bg-surface-soft p-1">
      {options.map((o) => (
        <ToggleGroup.Item key={o.value} value={o.value}
          className="h-7 rounded-sm px-3 text-sm text-ink-2 transition data-[state=on]:bg-surface data-[state=on]:font-medium data-[state=on]:text-accent data-[state=on]:shadow-sm hover:text-ink">
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
