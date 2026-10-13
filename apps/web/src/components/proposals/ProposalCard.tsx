import type { ProposalItem } from "../../api/types";
import { OPERATION, STATUS } from "./elementMeta";
import { REVIEW_FIELD_LABELS, reviewChanges, reviewKindName, valueText } from "./reviewMeta";
import { ReviewIcon } from "./ReviewIcon";

export type CardActions = {
  accept: (item: ProposalItem) => void;
  reject: (item: ProposalItem) => void;
  restore: (item: ProposalItem) => void;
  open: (item: ProposalItem, source?: HTMLElement) => void;
};

export function ProposalActions({ item, busy, blocked, actions, modal = false }: {
  item: ProposalItem;
  busy: boolean;
  blocked: string;
  actions: CardActions;
  modal?: boolean;
}) {
  if (item.status === "superseded") return null;
  if (item.status === "rejected") return <button type="button" className="btn" disabled={busy}
    aria-label={`恢复 ${item.display_name}`} onClick={() => actions.restore(item)}>恢复</button>;
  if (item.status === "accepted") return <button type="button" className={`btn ${modal ? "" : "reject"}`}
    disabled={busy} aria-label={`拒绝并撤销 ${item.display_name}`}
    title="撤销已接受的修改，并一并拒绝依赖此项的已接受提案"
    onClick={() => actions.reject(item)}>拒绝</button>;
  return <>
    <button type="button" className={`btn ${modal ? "primary" : "accept"}`}
      disabled={busy || !!blocked} title={blocked || "接受此提案"}
      aria-label={`接受 ${item.display_name}`} onClick={() => actions.accept(item)}>接受</button>
    <button type="button" className={`btn ${modal ? "" : "reject"}`} disabled={busy}
      aria-label={`拒绝 ${item.display_name}`} onClick={() => actions.reject(item)}>拒绝</button>
  </>;
}

export function ProposalCard({ item, technical, error, busy, actions, blocked, selected, onSelect, onEvidence, evidenceOpen }: {
  item: ProposalItem;
  technical: string;
  error?: string;
  busy: boolean;
  actions: CardActions;
  blocked: string;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onEvidence: (anchor: HTMLElement) => void;
  evidenceOpen: boolean;
}) {
  const changes = reviewChanges(item);
  const change = changes.find((entry) => entry.path === "name") ?? changes[0];
  const before = change ? valueText(change.before) : "无内容改动";
  const after = change ? valueText(change.after) : "补充证据";
  const isBlocked = ["conflict", "stale"].includes(item.status);
  return <article className={`proposal-row${selected ? " is-selected" : ""}${isBlocked ? " is-blocked" : ""}`}
    tabIndex={0} data-row={item.id} aria-haspopup="dialog"
    aria-label={`${reviewKindName(item.target_kind)} ${technical}，${OPERATION[item.operation]}，${STATUS[item.status]}。按 Enter 查看详情`}
    onClick={(event) => { if (!(event.target as HTMLElement).closest("button,input")) actions.open(item, event.currentTarget); }}
    onKeyDown={(event) => {
      if (event.target === event.currentTarget && event.key === "Enter") {
        event.preventDefault(); actions.open(item, event.currentTarget);
      }
    }}>
    <input className="row-check" type="checkbox" checked={selected} aria-label={`选择 ${item.display_name}`}
      onChange={(event) => onSelect(event.target.checked)} />
    <div className="row-identity">
      <span className={`kind ${item.target_kind}`}>{reviewKindName(item.target_kind)} ·</span>
      <code className="technical" title={technical}>{technical}</code>
      <span className={`op ${item.operation}`}>{OPERATION[item.operation]}</span>
      {item.status !== "pending" && <span className={`state ${item.status}`}>{item.status === "accepted" ? "✓ " : ""}{STATUS[item.status]}</span>}
      <button type="button" className="icon-btn" aria-haspopup="dialog" aria-expanded={evidenceOpen}
        aria-label={`查看 ${item.display_name} 的证据（${item.evidence.length} 条）`}
        title={`查看材料证据 · ${item.evidence.length} 条`} onClick={(event) => onEvidence(event.currentTarget)}>
        <ReviewIcon name="evidence" />
      </button>
    </div>
    <div className="diff-summary" title={`${REVIEW_FIELD_LABELS[change?.path] ?? change?.path ?? "名称"}：${before} → ${after}`}>
      <span className="old-value">{before}</span><span className="diff-arrow" aria-hidden="true">→</span>
      <strong className="new-value">{after}</strong>{changes.length > 1 && <span className="extra-changes">+{changes.length - 1}</span>}
    </div>
    <div className="row-actions" onClick={(event) => event.currentTarget.closest<HTMLElement>("[data-row]")?.focus({ preventScroll: true })}>
      <ProposalActions item={item} busy={busy} blocked={blocked} actions={actions} />
    </div>
    {isBlocked && <div className="block-reason" title={item.status_reason}>{item.status_reason || "当前目标已发生变化，请重新评估"}</div>}
    {error && <p className="row-error" role="alert">{error}</p>}
  </article>;
}
