import { Tooltip } from "antd";
import { Info, type LucideIcon } from "lucide-react";

/** An icon that explains itself on hover or focus. */
export function HintIcon({ text, icon: Icon = Info }: { text: string; icon?: LucideIcon }) {
  return (
    <Tooltip title={text}>
      <span className="inline-flex cursor-help text-muted" tabIndex={0} role="img" aria-label={text}>
        <Icon size={14} aria-hidden="true" />
      </span>
    </Tooltip>
  );
}

export function HintedHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex items-center gap-1">
      <h3 className="m-0 text-sm font-semibold">{title}</h3>
      <HintIcon text={hint} />
    </div>
  );
}
