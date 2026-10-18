import { Tooltip } from "antd";
import { Lock } from "lucide-react";
import type { BindingStatus } from "../../api/types";
import { BINDING_STATUS } from "../../lib/objectMapping";
import { StatusMark, type StatusState } from "../layout/StatusMark";

const COLOR_STATE: Record<string, StatusState> = {
  success: "mapped",
  warning: "partial",
  error: "error",
};

export function MappingStatusIcon({
  state,
  label,
}: {
  state: StatusState;
  label?: string;
}) {
  return <StatusMark state={state} label={label} />;
}

export function BindingStatusTag({ status }: { status: BindingStatus }) {
  const { color, text } = BINDING_STATUS[status];
  return <StatusMark state={COLOR_STATE[color] ?? "unmapped"} label={text} />;
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
