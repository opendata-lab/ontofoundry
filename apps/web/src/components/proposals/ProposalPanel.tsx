import { useMemo, useState } from "react";
import type { ModelingSession, ProposalItem } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { EmptyModel } from "../EmptyModel";
import { ProposalCard, type CardActions } from "./ProposalCard";
import { ProposalDetail } from "./ProposalDetail";
import { acceptableIds, itemTitle } from "./elementMeta";

type Filter = "all" | "blocked" | "update" | "delete" | "create";

const GROUPS: { key: string; title: string; match: (i: ProposalItem) => boolean }[] = [
  { key: "blocked", title: "冲突 / 已过期", match: (i) => i.status === "stale" || i.status === "conflict" },
  { key: "update", title: "修改", match: (i) => i.status === "pending" && i.operation === "update" },
  { key: "delete", title: "删除", match: (i) => i.status === "pending" && i.operation === "delete" },
  { key: "create", title: "新增", match: (i) => i.status === "pending" && i.operation === "create" },
];

export function ProposalPanel({
  session,
  proposals,
  running,
  onRemodel,
}: {
  session: ModelingSession | null;
  proposals: ProposalsState;
  running: boolean;
  onRemodel: (text: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);
  const { detail, batches } = proposals;
  const items = useMemo(() => detail?.items ?? [], [detail]);
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items]);

  if (!session || (!batches.length && !running))
    return (
      <div className="proposal-panel">
        <EmptyModel text="向智能体描述场景并开始建模，提案会出现在这里" />
      </div>
    );

  const decideGroup = (item: ProposalItem, decision: "accept" | "reject" | "restore") => {
    const ids =
      decision === "accept"
        ? item.dependency_group.filter((id) => byId.get(id)?.status === "pending")
        : [item.id];
    return proposals.decide(ids.map((proposal_id) => ({ proposal_id, decision })));
  };
  const actions: CardActions = {
    accept: (item) => void decideGroup(item, "accept"),
    reject: (item) => void decideGroup(item, "reject"),
    restore: (item) => void decideGroup(item, "restore"),
    open: (item) => setOpen(item.id),
    remodel: (item) =>
      onRemodel(
        `请基于当前草稿重新评估以下已过期的提案：${itemTitle(item)}（${item.status_reason || "目标已变化"}）`,
      ),
  };

  const counts = {
    blocked: items.filter(GROUPS[0].match).length,
    update: items.filter(GROUPS[1].match).length,
    delete: items.filter(GROUPS[2].match).length,
    create: items.filter(GROUPS[3].match).length,
  };
  const pending = items.filter((i) => i.status === "pending").length;
  const acceptable = acceptableIds(items);
  const rejectable = items.filter((i) => ["pending", "stale", "conflict"].includes(i.status));
  const history = items.filter((i) => ["accepted", "rejected", "superseded"].includes(i.status));
  const visible = GROUPS.filter((g) => filter === "all" || filter === g.key);
  const drifted =
    detail && detail.source_session_revision !== session.revision && counts.blocked > 0;
  const openItem = open ? byId.get(open) : undefined;

  return (
    <div className="proposal-panel">
      {running && <p className="proposal-running" role="status">正在生成提案…</p>}
      {detail && (
        <header className="proposal-batch">
          <div>
            {batches.length > 1 ? (
              <select
                aria-label="提案批次"
                value={detail.id}
                onChange={(e) => proposals.select(e.target.value)}
              >
                {batches.map((b, index) => (
                  <option key={b.id} value={b.id}>
                    批次 #{batches.length - index} ·{" "}
                    {new Date(b.created_at).toLocaleTimeString("zh-CN", { hour12: false })}
                  </option>
                ))}
              </select>
            ) : (
              <strong>批次 #1</strong>
            )}
            <span>
              {" "}
              · 基于草稿 r{detail.source_session_revision} · {pending} 条待审
            </span>
          </div>
          <div className="proposal-batch-actions">
            <button
              type="button"
              className="button button--primary"
              disabled={proposals.busy || !acceptable.length}
              onClick={() =>
                void proposals.decide(acceptable.map((proposal_id) => ({ proposal_id, decision: "accept" })))
              }
            >
              接受全部无冲突项
            </button>
            <button
              type="button"
              className="button button--secondary"
              disabled={proposals.busy || !rejectable.length}
              onClick={() =>
                void proposals.decide(rejectable.map((i) => ({ proposal_id: i.id, decision: "reject" })))
              }
            >
              全部拒绝
            </button>
          </div>
        </header>
      )}
      {detail?.status === "failed" && (
        <div className="inline-error" role="alert">
          提案结果被拒收：{detail.error?.message}
          <button type="button" className="button button--text" onClick={() => onRemodel("请重新建模并按提案格式输出。")}>
            重新建模
          </button>
        </div>
      )}
      {drifted && (
        <p className="proposal-drift" role="status">
          生成期间草稿已变化（r{detail!.source_session_revision} → r{session.revision}），受影响的提案已标为已过期
        </p>
      )}
      {proposals.error && (
        <p className="inline-error" role="alert">
          {proposals.error}
        </p>
      )}
      {items.length > 0 && (
        <div className="proposal-filter" role="radiogroup" aria-label="筛选提案">
          {(
            [
              ["all", "全部", items.length - history.length],
              ["blocked", "冲突", counts.blocked],
              ["update", "修改", counts.update],
              ["delete", "删除", counts.delete],
              ["create", "新增", counts.create],
            ] as [Filter, string, number][]
          ).map(([key, label, count]) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={filter === key}
              className={`chip chip--${key}`}
              onClick={() => setFilter(key)}
            >
              {label} <b>{count}</b>
            </button>
          ))}
        </div>
      )}
      <div className="proposal-groups">
        {visible.map((group) => {
          const groupItems = items.filter(group.match);
          if (!groupItems.length) return null;
          return (
            <section key={group.key} className={`proposal-group proposal-group--${group.key}`}>
              <h3>
                {group.title} <small>{groupItems.length}</small>
              </h3>
              {groupItems.map((item) => (
                <ProposalCard
                  key={item.id}
                  item={item}
                  busy={proposals.busy}
                  error={proposals.itemErrors[item.id]}
                  actions={actions}
                  pendingGroup={
                    item.dependency_group.filter((id) => byId.get(id)?.status === "pending").length
                  }
                />
              ))}
            </section>
          );
        })}
        {history.length > 0 && filter === "all" && (
          <details className="proposal-group proposal-group--history">
            <summary>
              历史 <small>{history.length}</small>
            </summary>
            {history.map((item) => (
              <ProposalCard key={item.id} item={item} busy={proposals.busy} actions={actions} />
            ))}
          </details>
        )}
      </div>
      {openItem && detail && (
        <ProposalDetail
          item={openItem}
          items={items}
          workspaceId={session.workspace_id}
          sourceRevision={detail.source_session_revision}
          busy={proposals.busy}
          error={proposals.itemErrors[openItem.id]}
          actions={actions}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}
