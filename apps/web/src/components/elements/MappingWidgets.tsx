import { Tag, Tooltip } from "antd";
import { Lock } from "lucide-react";
import type { BindingStatus } from "../../api/types";
import { BINDING_STATUS } from "../../lib/objectMapping";

const MAPPING_STATE = {
  mapped: { color: "success", text: "已映射" },
  partial: { color: "warning", text: "部分映射" },
  unmapped: { color: "default", text: "未映射" },
} as const;

export function MappingStatusIcon({
  state,
  label,
}: {
  state: "mapped" | "partial" | "unmapped";
  label?: string;
}) {
  const { color, text } = MAPPING_STATE[state];
  return (
    <Tag color={color} className="!m-0">
      {label ?? text}
    </Tag>
  );
}


export function BindingStatusTag({ status }: { status: BindingStatus }) {
  const { color, text } = BINDING_STATUS[status];
  return (
    <Tag color={color} className="!m-0">
      {text}
    </Tag>
  );
}


export function ReadonlyIcon({ reason }: { reason: string | null }) {
  return reason ? (
    <Tooltip title={reason}>
      <span className="inline-flex text-muted" aria-label={`只读：${reason}`} role="img">
        <Lock size={14} />
      </span>
    </Tooltip>
  ) : null;
}
