import type { ProposalItem } from "../../api/types";
import { EvidenceLine } from "./EvidenceQuote";
import { FieldDiff } from "./FieldDiff";
import { itemTitle, KIND, OPERATION, STATUS } from "./elementMeta";

export type CardActions = {
  accept: (item: ProposalItem) => void;
  reject: (item: ProposalItem) => void;
  restore: (item: ProposalItem) => void;
  open: (item: ProposalItem) => void;
  remodel: (item: ProposalItem) => void;
  viewElement?: (item: ProposalItem) => void;
  canViewElement?: (item: ProposalItem) => boolean;
};

export function ProposalCard({
  item,
  error,
  busy,
  actions,
  pendingGroup = item.dependency_group.length,
}: {
  item: ProposalItem;
  error?: string;
  busy: boolean;
  actions: CardActions;
  /** Members of the dependency group still to accept, the item included. */
  pendingGroup?: number;
}) {
  const kind = KIND[item.target_kind];
  const Icon = kind.icon;
  const groupSize = pendingGroup;
  const blocked = item.status === "stale" || item.status === "conflict";
  return (
    <article
      className={`proposal-card proposal-card--${item.status}`}
      aria-label={`${OPERATION[item.operation]} ${itemTitle(item)}`}
    >
      <span className={`model-icon model-icon--${kind.cls}`} aria-hidden>
        <Icon size={15} />
      </span>
      <div className="proposal-card-body">
        <button type="button" className="proposal-card-title" onClick={() => actions.open(item)}>
          <b className={`op op--${item.operation}`}>{OPERATION[item.operation]}</b>{" "}
          {itemTitle(item)}
        </button>
        <div className="proposal-card-tags">
          {item.status !== "pending" && (
            <span className={`tag tag--${item.status}`}>
              {STATUS[item.status]}
              {item.status === "accepted" && item.accepted_revision
                ? ` → r${item.accepted_revision}`
                : ""}
            </span>
          )}
          {item.target_kind === "action" && <span className="tag">仅定义 · 不可执行</span>}
          {groupSize > 1 && item.status === "pending" && (
            <span className="tag tag--group">依赖组 {groupSize} 项</span>
          )}
        </div>
        {item.status_reason && <p className="proposal-reason">{item.status_reason}</p>}
        {item.operation === "update" && (
          <FieldDiff changes={item.field_changes.length ? item.field_changes : []} limit={3} />
        )}
        {item.reason && <p className="muted">{item.reason}</p>}
        {item.evidence[0] && <EvidenceLine evidence={item.evidence[0]} />}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="proposal-card-actions">
        {actions.viewElement && <button type="button" className="button button--text" disabled={busy || actions.canViewElement?.(item) === false} title={actions.canViewElement?.(item) === false ? "此元素尚未加入草稿或已被删除，请查看提案详情" : undefined} onClick={() => actions.viewElement?.(item)}>查看元素</button>}
        {item.status === "pending" && (
          <>
            <button
              type="button"
              className="button button--primary"
              disabled={busy}
              onClick={() => actions.accept(item)}
            >
              {groupSize > 1 ? "接受整组" : "接受"}
            </button>
            <button type="button" className="button button--secondary" disabled={busy} onClick={() => actions.reject(item)}>
              拒绝
            </button>
          </>
        )}
        {blocked && (
          <>
            <button type="button" className="button button--secondary" disabled={busy} onClick={() => actions.remodel(item)}>
              基于当前草稿重新建模
            </button>
            <button type="button" className="button button--text" disabled={busy} onClick={() => actions.reject(item)}>
              拒绝
            </button>
          </>
        )}
        {item.status === "rejected" && (
          <button type="button" className="button button--text" disabled={busy} onClick={() => actions.restore(item)}>
            恢复
          </button>
        )}
      </div>
    </article>
  );
}
