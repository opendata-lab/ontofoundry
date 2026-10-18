import { Check, Clock, Minus, Pencil, TriangleAlert } from "lucide-react";
import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from "react";

const STATUS_META = {
  mapped: { icon: Check, text: "已映射", colorClass: "text-success" },
  partial: { icon: TriangleAlert, text: "部分映射", colorClass: "text-warning" },
  unmapped: { icon: Minus, text: "未映射", colorClass: "text-muted" },
  info: { icon: Pencil, text: "已修改", colorClass: "text-accent" },
  pending: { icon: Clock, text: "待审", colorClass: "text-muted" },
  error: { icon: TriangleAlert, text: "异常", colorClass: "text-danger" },
} as const;

export type StatusState = keyof typeof STATUS_META;

/**
 * Compact status indicator using a small icon and 12px text colored by
 * semantic state, without bordered tag boxes that compete with primary text.
 */
export const StatusMark = forwardRef<HTMLSpanElement, {
  state: StatusState;
  label?: ReactNode;
} & Omit<ComponentPropsWithoutRef<"span">, "children">>(function StatusMark({
  state,
  label,
  className = "",
  ...props
}, ref) {
  const { icon: Icon, text, colorClass } = STATUS_META[state];
  return (
    <span {...props} ref={ref} className={`inline-flex items-center gap-1 text-xs leading-tight ${colorClass} ${className}`.trim()}>
      <Icon size={13} className="flex-none" />
      <span>{label ?? text}</span>
    </span>
  );
});
