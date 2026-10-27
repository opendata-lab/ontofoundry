import { fieldLabel } from "./elementMeta";
import { Button, Checkbox, Popover, Tag, Tooltip, Typography } from "antd";
import { FileText } from "lucide-react";
import type { ProposalItem, ProposalStatus } from "../../api/types";
import { OPERATION, STATUS } from "./elementMeta";
import { StatusMark, type StatusState } from "../layout";
import { ReviewEvidence } from "./EvidencePopover";
import { requiredIds, reviewChanges, reviewKindName, valueText } from "./reviewMeta";

const { Text } = Typography;

const REVIEW_STATE: Record<ProposalStatus, StatusState> = {
  pending: "pending",
  accepted: "mapped",
  rejected: "unmapped",
};

export function ProposalStatusMark({ status }: { status: ProposalStatus }) {
  return <StatusMark state={REVIEW_STATE[status]} label={STATUS[status]} />;
}

export type CardActions = {
  accept: (item: ProposalItem) => void;
  reject: (item: ProposalItem) => void;
  restore: (item: ProposalItem) => void;
  open: (item: ProposalItem) => void;
};

export function ProposalActions({
  item,
  busy,
  blocked,
  actions,
  size = "small",
}: {
  item: ProposalItem;
  busy: boolean;
  blocked: string;
  actions: CardActions;
  size?: "small" | "middle";
}) {
  if (item.status === "rejected")
    return (
      <Button size={size} disabled={busy} aria-label={`恢复 ${item.display_name}`} onClick={() => actions.restore(item)}>
        恢复
      </Button>
    );
  if (item.status === "accepted")
    return (
      <Tooltip title="撤销已接受的修改，并一并拒绝依赖此项的已接受提案">
        <Button size={size} disabled={busy} aria-label={`拒绝并撤销 ${item.display_name}`} onClick={() => actions.reject(item)}>
          拒绝
        </Button>
      </Tooltip>
    );
  return (
    <>
      <Tooltip title={blocked || undefined}>
        <Button
          size={size}
          type="primary"
          disabled={busy || !!blocked}
          aria-label={`接受 ${item.display_name}`}
          onClick={() => actions.accept(item)}
        >
          接受
        </Button>
      </Tooltip>
      <Button size={size} danger disabled={busy} aria-label={`拒绝 ${item.display_name}`} onClick={() => actions.reject(item)}>
        拒绝
      </Button>
    </>
  );
}

export function ProposalCard({
  item,
  items,
  technical,
  error,
  busy,
  actions,
  blocked,
  selected,
  onSelect,
}: {
  item: ProposalItem;
  items?: ProposalItem[];
  technical: string;
  error?: string;
  busy: boolean;
  actions: CardActions;
  blocked: string;
  selected: boolean;
  onSelect: (checked: boolean) => void;
}) {
  const changes = reviewChanges(item);
  const change = changes.find((entry) => entry.path === "name") ?? changes[0];
  const before = change ? valueText(change.before) : "无内容改动";
  const after = change ? valueText(change.after) : "补充证据";
  const deps = requiredIds(item);
  const depNames = deps.map((id) => items?.find((entry) => entry.id === id)?.display_name ?? id).join("、");
  return (
    <article
      tabIndex={0}
      data-row={item.id}
      aria-label={`${reviewKindName(item.target_kind)} ${technical}，${OPERATION[item.operation]}，${STATUS[item.status]}。按 Enter 查看详情`}
      className={`flex cursor-pointer items-start gap-2 border-b border-rule-soft px-4 py-2 outline-none hover:bg-surface-soft focus-visible:bg-accent-soft ${selected ? "bg-accent-soft" : ""}`}
      onClick={(event) => {
        if (!(event.target as HTMLElement).closest("button,input,label,.ant-popover")) actions.open(item);
      }}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && event.key === "Enter") {
          event.preventDefault();
          actions.open(item);
        }
      }}
    >
      <Checkbox checked={selected} aria-label={`选择 ${item.display_name}`} onChange={(e) => onSelect(e.target.checked)} />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          <Tag className="m-0">
            {reviewKindName(item.target_kind)}
          </Tag>
          <code className="truncate text-xs" title={technical}>
            {technical}
          </code>
          <Tag className="m-0">{OPERATION[item.operation]}</Tag>
          {item.status !== "pending" && (
            <ProposalStatusMark status={item.status} />
          )}
          {deps.length > 0 && (
            <Tooltip title={depNames}>
              <Tag className="m-0">联动 {deps.length} 项</Tag>
            </Tooltip>
          )}
          {item.duplicate_candidates.length > 0 && item.status === "pending" && (
            <Tooltip title="可能与已有实例重复，打开详情可改为更新已有实例">
              <StatusMark state="partial" label="可能重复" />
            </Tooltip>
          )}
          <Popover
            trigger="click"
            placement="bottomLeft"
            title="材料证据"
            content={
              <div className="max-h-review-code w-review-evidence max-w-full overflow-auto">
                <ReviewEvidence evidence={item.evidence} />
              </div>
            }
          >
            <Button
              size="small"
              type="text"
              aria-label={`查看 ${item.display_name} 的证据（${item.evidence.length} 条）`}
              icon={<FileText size={13} />}
            >
              {item.evidence.length}
            </Button>
          </Popover>
        </div>
        <div
          className="flex min-w-0 items-center gap-1 text-xs"
          title={`${fieldLabel(change?.path ?? "display_name")}：${before} → ${after}`}
        >
          <Text type="secondary" className="max-w-2/5 truncate line-through">
            {before}
          </Text>
          <Text type="secondary">→</Text>
          <strong className="truncate">{after}</strong>
          {changes.length > 1 && <Text type="secondary">+{changes.length - 1}</Text>}
        </div>
        { item.status === "pending" && blocked.startsWith("数据来源未就绪") && (
          <Text type="danger" className="text-xs" title={blocked}>
            {blocked}
          </Text>
        )}
        {error && (
          <Text type="danger" role="alert" className="text-xs">
            {error}
          </Text>
        )}
      </div>
      <div className="flex shrink-0 gap-1">
        <ProposalActions item={item} busy={busy} blocked={blocked} actions={actions} />
      </div>
    </article>
  );
}
