import { Check, Minus, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

const STATUS_META = {
  mapped: { icon: Check, text: "已映射", colorClass: "text-success" },
  partial: { icon: TriangleAlert, text: "部分映射", colorClass: "text-warning" },
  unmapped: { icon: Minus, text: "未映射", colorClass: "text-muted" },
  error: { icon: TriangleAlert, text: "异常", colorClass: "text-danger" },
} as const;

export type StatusState = keyof typeof STATUS_META;

/**
 * Compact status indicator using a small icon and 12px text colored by
 * semantic state, without bordered tag boxes that compete with primary text.
 */
export function StatusMark({
  state,
  label,
  className = "",
}: {
  state: StatusState;
  label?: ReactNode;
  className?: string;
}) {
  const { icon: Icon, text, colorClass } = STATUS_META[state];
  return (
    <span className={`inline-flex items-center gap-1 text-xs leading-tight ${colorClass} ${className}`.trim()}>
      <Icon size={13} className="flex-none" />
      <span>{label ?? text}</span>
    </span>
  );
}
