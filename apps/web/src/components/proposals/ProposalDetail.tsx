import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ProposalItem } from "../../api/types";
import type { CardActions } from "./ProposalCard";
import { EvidenceQuote } from "./EvidenceQuote";
import { FieldDiff } from "./FieldDiff";
import { itemTitle, OPERATION, STATUS } from "./elementMeta";

export function ProposalDetail({
  item,
  items,
  workspaceId,
  sourceRevision,
  busy,
  error,
  actions,
  onClose,
}: {
  item: ProposalItem;
  items: ProposalItem[];
  workspaceId: string;
  sourceRevision: number;
  busy: boolean;
  error?: string;
  actions: CardActions;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current;
    if (el && !el.open) el.showModal?.();
    return () => el?.close?.();
  }, []);
  const byId = new Map(items.map((i) => [i.id, i]));
  const deps = item.dependency_group.filter((id) => id !== item.id).map((id) => byId.get(id)).filter(Boolean) as ProposalItem[];
  const changes =
    item.operation === "update"
      ? item.field_changes
      : Object.entries(item.after ?? item.before ?? {})
          .filter(([key]) => !["id", "evidence"].includes(key))
          .map(([path, value]) =>
            item.operation === "create"
              ? { path, before: null, after: value }
              : { path, before: value, after: null },
          );
  return (
    <dialog ref={dialog} className="proposal-drawer" aria-label="提案详情" onClose={onClose}>
      <header>
        <div>
          <h2>
            {OPERATION[item.operation]} {itemTitle(item)}
          </h2>
          <small>基于草稿 r{sourceRevision}</small>
        </div>
        <span className={`tag tag--${item.status}`}>{STATUS[item.status]}</span>
        <button type="button" className="icon-button" aria-label="关闭详情" onClick={onClose}>
          <X size={16} />
        </button>
      </header>
      <div className="proposal-drawer-body">
        {item.status_reason && <p className="proposal-reason">{item.status_reason}</p>}
        <section>
          <h3>字段差异</h3>
          <FieldDiff
            changes={changes}
            beforeLabel={`草稿当前值 r${sourceRevision}`}
            afterLabel="提案值"
          />
        </section>
        {item.reason && (
          <section>
            <h3>理由</h3>
            <p>{item.reason}</p>
          </section>
        )}
        <section>
          <h3>证据</h3>
          {item.evidence.length ? (
            item.evidence.map((ev) => <EvidenceQuote key={ev.id} evidence={ev} workspaceId={workspaceId} />)
          ) : (
            <p className="muted">没有附带证据</p>
          )}
        </section>
        {deps.length > 0 && (
          <section>
            <h3>依赖</h3>
            <ul className="proposal-deps">
              {deps.map((dep) => (
                <li key={dep.id}>
                  {OPERATION[dep.operation]} {itemTitle(dep)} <span className={`tag tag--${dep.status}`}>{STATUS[dep.status]}</span>
                </li>
              ))}
            </ul>
            <small className="muted">接受时将一并接受</small>
          </section>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer>
        {item.status === "rejected" ? (
          <button type="button" className="button button--secondary" disabled={busy} onClick={() => actions.restore(item)}>
            恢复
          </button>
        ) : (
          <>
            <button
              type="button"
              className="button button--secondary"
              disabled={busy || !["pending", "stale", "conflict"].includes(item.status)}
              onClick={() => actions.reject(item)}
            >
              拒绝
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={busy || item.status !== "pending"}
              onClick={() => actions.accept(item)}
            >
              {item.dependency_group.length > 1 ? "接受整组" : "接受"}
            </button>
          </>
        )}
      </footer>
    </dialog>
  );
}
