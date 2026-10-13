import { X } from "lucide-react";
import type { ProposalItem } from "../../api/types";
import { ProposalActions, type CardActions } from "./ProposalCard";
import { ReviewEvidence } from "./EvidencePopover";
import { OPERATION, STATUS } from "./elementMeta";
import { acceptanceBlock, requiredIds, REVIEW_FIELD_LABELS, reviewChanges, reviewKindName, valueText } from "./reviewMeta";
import { ReviewDialog } from "./ReviewOverlays";

export function ProposalDetail({ item, items, technical, busy, error, actions, onClose }: {
  item: ProposalItem;
  items: ProposalItem[];
  technical: string;
  busy: boolean;
  error?: string;
  actions: CardActions;
  onClose: () => void;
}) {
  const byId = new Map(items.map((entry) => [entry.id, entry]));
  const deps = requiredIds(item);
  const changes = reviewChanges(item);
  const reason = item.reason.trim();
  const blocked = acceptanceBlock(item, byId);
  return <ReviewDialog className="detail-dialog" label="提案详情" onClose={onClose}>
    <header className="modal-header"><div>
      <h2>{OPERATION[item.operation]}{reviewKindName(item.target_kind)} · {item.display_name}</h2>
      <small>{technical}</small>
    </div><span className={`state ${item.status}`}>{STATUS[item.status]}</span>
      <button type="button" className="icon-btn" data-initial-focus aria-label="关闭提案详情" onClick={onClose}><X /></button>
    </header>
    <div className="modal-body">
      {["conflict", "stale"].includes(item.status) && <div className="warning-box">{STATUS[item.status]}：{item.status_reason || "当前目标已发生变化，请重新评估"}</div>}
      <section><div className="section-heading"><h3>字段差异</h3><small>{changes.length} 处改动</small></div>
        <table className="diff-table"><thead><tr><th scope="col">字段</th><th scope="col">修改前</th><th scope="col">提案值</th></tr></thead>
          <tbody>{changes.map((change) => <tr key={change.path}>
            <th scope="row">{REVIEW_FIELD_LABELS[change.path] ?? change.path}</th>
            <td className="before-cell"><del>{valueText(change.before)}</del></td>
            <td className="after-cell"><ins>{valueText(change.after)}</ins></td>
          </tr>)}</tbody>
        </table>
      </section>
      {reason && <section><div className="section-heading"><h3>提案理由</h3></div><p>{reason}</p></section>}
      <section><div className="section-heading"><h3>材料证据</h3><small>{item.evidence.length} 条引用</small></div>
        <ReviewEvidence evidence={item.evidence} />
      </section>
      <section><div className="section-heading"><h3>依赖关系</h3></div>
        {deps.length ? <><ul className="dependency-list">{deps.map((id) => {
          const dependency = byId.get(id);
          return <li key={id}>{dependency ? <>
            <button type="button" onClick={() => actions.open(dependency)}>{reviewKindName(dependency.target_kind)} · {dependency.display_name}</button>
            <span className={`state ${dependency.status}`}>{dependency.status === "accepted" ? "✓ " : ""}{STATUS[dependency.status]}</span>
          </> : <span className="warning-box">依赖提案缺失，暂不可接受</span>}</li>;
        })}</ul><p className="muted">接受时会一并接受尚待审核的依赖；撤销时会同步拒绝依赖此项的已接受提案。</p></> :
          <p className="muted">本提案无依赖，可独立审核。</p>}
      </section>
      {error && <p className="warning-box" role="alert">{error}</p>}
    </div>
    <footer className="modal-footer">
      <small>{item.status === "accepted" ? "已接受。拒绝将撤销此项修改。" : item.status === "rejected" ?
        "恢复后回到待审；冲突项会保留原标记。" : blocked || "接受后将更新本体草稿。"}</small>
      <div className="actions" onClick={(event) => event.currentTarget.closest("dialog")?.querySelector<HTMLElement>("[data-initial-focus]")?.focus({ preventScroll: true })}>
        <ProposalActions item={item} busy={busy} blocked={blocked} actions={actions} modal />
      </div>
    </footer>
  </ReviewDialog>;
}
