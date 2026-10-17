import { Alert, Button, Checkbox, Dropdown, Empty, Input, Modal, Segmented, Select, Tooltip, Typography } from "antd";
import { MoreHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ModelingSession, ProposalItem, TargetKind } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { ProposalCard, type CardActions } from "./ProposalCard";
import { ProposalDetail } from "./ProposalDetail";
import { acceptanceBlock, decisionIds, reviewKindName, searchText, technicalName, type ReviewDecision } from "./reviewMeta";

const { Text } = Typography;

type Props = {
  session: ModelingSession | null;
  proposals: ProposalsState;
  running: boolean;
  onRemodel: (text: string) => void;
};
type StatusFilter = "pending" | "accepted" | "rejected" | "blocked";
const STATUSES: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "待审" },
  { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" },
  { key: "blocked", label: "冲突" },
];
const KIND_ORDER: TargetKind[] = [
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
  "mapping",
  "material_object",
  "material_link",
];
const matchesStatus = (item: ProposalItem, status: StatusFilter) =>
  status === "blocked" ? ["stale", "conflict"].includes(item.status) : item.status === status;

export function ProposalPanel(props: Props) {
  if (!props.session || (!props.proposals.batches.length && !props.running))
    return <Empty className="mt-12" description="向智能体描述场景并开始建模，提案会出现在这里" />;
  return (
    <ProposalReview key={`${props.session.id}:${props.proposals.detail?.id ?? "loading"}`} {...props} session={props.session} />
  );
}

function ProposalReview({ session, proposals, running, onRemodel }: Props & { session: ModelingSession }) {
  const { detail } = proposals;
  const items = useMemo(() => detail?.items ?? [], [detail]);
  const byId = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const kinds = KIND_ORDER.filter((kind) => items.some((item) => item.target_kind === kind));
  const [kindFilter, setKindFilter] = useState<TargetKind[]>([]);
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(new Set<string>());
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);
  const [toast, setToast] = useState("");
  const [undoSteps, setUndoSteps] = useState<Parameters<ProposalsState["decide"]>[0][]>([]);
  const [undoBusy, setUndoBusy] = useState(false);
  const submitting = useRef(false);
  const busy = proposals.busy || undoBusy;
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matchesKind = (item: ProposalItem) => !kindFilter.length || kindFilter.includes(item.target_kind);
  const matchesSearch = (item: ProposalItem) => {
    if (!terms.length) return true;
    const text = searchText(item, items, session.draft);
    return terms.every((term) => text.includes(term));
  };
  const visible = items.filter((item) => matchesKind(item) && matchesSearch(item) && matchesStatus(item, status));
  const statusBase = items.filter((item) => matchesKind(item) && matchesSearch(item));
  const hasConflicts = items.some((item) => matchesStatus(item, "blocked"));
  const statusChoices = STATUSES.filter((tab) => tab.key !== "blocked" || hasConflicts || status === "blocked");
  const acceptable = items.filter((item) => item.status === "pending" && !acceptanceBlock(item, byId));
  const rejectable = items.filter((item) => ["pending", "stale", "conflict"].includes(item.status));
  const selectedIds = [...selected].filter((id) => byId.has(id));
  const selectedVisible = visible.filter((item) => selected.has(item.id)).length;
  const hasFilters = !!kindFilter.length || !!terms.length || status !== "pending";
  // Every decision bumps the session revision, so a moved revision alone is
  // normal; warn only when it actually left proposals stale or conflicting.
  const drifted = !!detail && hasConflicts && detail.source_session_revision !== session.revision;
  const openItem = openId ? byId.get(openId) : undefined;
  useEffect(() => {
    if (!toast || undoBusy) return;
    const timer = window.setTimeout(() => setToast(""), 7000);
    return () => window.clearTimeout(timer);
  }, [toast, undoBusy]);
  const clearFilters = () => {
    setQuery("");
    setKindFilter([]);
    setStatus("pending");
  };
  const submit = async (requested: string[], decision: ReviewDecision) => {
    if (busy || submitting.current) return;
    const ids = decisionIds(items, requested, decision);
    if (!ids.length) return;
    submitting.current = true;
    const ok = await proposals.decide(ids.map((proposal_id) => ({ proposal_id, decision })));
    submitting.current = false;
    if (!ok) return;
    setSelected((current) => new Set([...current].filter((id) => !ids.includes(id))));
    const extra = ids.filter((id) => !requested.includes(id)).length;
    setToast(
      `${{ accept: "已接受", reject: "已拒绝", restore: "已恢复" }[decision]} ${ids.length} 条${extra ? `（含 ${extra} 条依赖项）` : ""}`,
    );
    const step = (values: string[], next: ReviewDecision) => values.map((proposal_id) => ({ proposal_id, decision: next }));
    // Reverse real decisions through the API, never overwrite a local snapshot.
    setUndoSteps(
      decision === "accept"
        ? [step(ids, "reject"), step(ids, "restore")]
        : decision === "restore"
          ? [step(ids, "reject")]
          : [step(ids, "restore"), step(ids.filter((id) => byId.get(id)?.status === "accepted"), "accept")].filter(
              (phase) => phase.length,
            ),
    );
  };
  const undo = async () => {
    if (busy || submitting.current || !undoSteps.length) return;
    submitting.current = true;
    setUndoBusy(true);
    try {
      for (let index = 0; index < undoSteps.length; index++) {
        if (!(await proposals.decide(undoSteps[index]))) {
          setUndoSteps(undoSteps.slice(index));
          setToast("撤销未完成，请重试");
          return;
        }
      }
      setUndoSteps([]);
      setToast("已撤销上次操作");
    } finally {
      submitting.current = false;
      setUndoBusy(false);
    }
  };
  const actions: CardActions = {
    accept: (item) => void submit([item.id], "accept"),
    reject: (item) => void submit([item.id], "reject"),
    restore: (item) => void submit([item.id], "restore"),
    open: (item) => setOpenId(item.id),
  };
  const toggle = (id: string, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  return (
    <div className="flex h-full min-h-0 flex-col gap-2" aria-label="提案审核面板" aria-busy={busy}>
      {running && <Alert type="info" showIcon message="正在生成提案…" />}
      {drifted && <Alert type="warning" showIcon message="草稿已更新，部分提案需要重新确认" />}
      {detail?.status === "failed" && (
        <Alert
          type="error"
          showIcon
          message={`提案结果被拒收：${detail.error?.message ?? ""}`}
          action={
            <Button size="small" disabled={running || busy} onClick={() => onRemodel("请重新建模并按提案格式输出。")}>
              重新建模
            </Button>
          }
        />
      )}
      {proposals.error && <Alert type="error" showIcon message={proposals.error} />}
      <Segmented
        size="small"
        className="self-start"
        value={status}
        onChange={(value) => setStatus(value as StatusFilter)}
        options={statusChoices.map((tab) => ({
          value: tab.key,
          label: `${tab.label} ${statusBase.filter((item) => matchesStatus(item, tab.key)).length}`,
        }))}
      />
      <div className="flex gap-2">
        <Input.Search
          allowClear
          size="small"
          aria-label="搜索提案名称"
          placeholder="搜索名称、技术名或所属对象…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Select
          mode="multiple"
          size="small"
          allowClear
          aria-label="元素类型"
          placeholder="全部类型"
          maxTagCount={1}
          className="min-w-[150px]"
          value={kindFilter}
          onChange={setKindFilter}
          options={kinds.map((kind) => ({
            value: kind,
            label: `${reviewKindName(kind)} ${items.filter((i) => i.target_kind === kind && matchesStatus(i, status)).length}`,
          }))}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 px-3">
        <Checkbox
          aria-label="选择当前筛选的全部提案"
          disabled={!visible.length}
          checked={visible.length > 0 && selectedVisible === visible.length}
          indeterminate={selectedVisible > 0 && selectedVisible < visible.length}
          onChange={(e) =>
            setSelected((current) => {
              const next = new Set(current);
              for (const item of visible) {
                if (e.target.checked) next.add(item.id);
                else next.delete(item.id);
              }
              return next;
            })
          }
        >
          {selectedIds.length ? `已选 ${selectedIds.length} 项` : "选择当前结果"}
        </Checkbox>
        <div className="ml-auto flex gap-1">
          {selectedIds.length ? (
            <>
              <Button
                size="small"
                disabled={busy || !selectedIds.some((id) => byId.get(id)?.status === "pending" && !acceptanceBlock(byId.get(id)!, byId))}
                onClick={() => void submit(selectedIds, "accept")}
              >
                接受选中
              </Button>
              <Button size="small" danger disabled={busy || !decisionIds(items, selectedIds, "reject").length} onClick={() => void submit(selectedIds, "reject")}>
                拒绝选中
              </Button>
              <Button size="small" type="text" onClick={() => setSelected(new Set())}>
                取消选择
              </Button>
            </>
          ) : (
            <Tooltip title={acceptable.length ? "接受全部可接受且无冲突的待审提案，不受当前筛选影响" : "没有可接受的无冲突待审提案"}>
              <span className="inline-flex">
                <Button
                  size="small"
                  type="primary"
                  disabled={busy || !acceptable.length}
                  onClick={() => void submit(acceptable.map((item) => item.id), "accept")}
                >
                  全部接受（{acceptable.length}）
                </Button>
              </span>
            </Tooltip>
          )}
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [{ key: "reject-all", label: "全部拒绝", danger: true, disabled: busy || !rejectable.length }],
              onClick: () => setConfirmReject(true),
            }}
          >
            <Button size="small" aria-label="更多批量操作" icon={<MoreHorizontal size={14} />} />
          </Dropdown>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-rule bg-surface" role="list">
        {visible.length ? (
          visible.map((item) => (
            <ProposalCard
              key={item.id}
              item={item}
              items={items}
              technical={technicalName(item, items, session.draft)}
              busy={busy}
              error={proposals.itemErrors[item.id]}
              blocked={acceptanceBlock(item, byId)}
              actions={actions}
              selected={selected.has(item.id)}
              onSelect={(checked) => toggle(item.id, checked)}
            />
          ))
        ) : (
          <Empty className="py-8" description={hasFilters ? "没有符合条件的提案" : "当前没有待审提案"}>
            {hasFilters && <Button onClick={clearFilters}>清除筛选</Button>}
          </Empty>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted">
        <span>
          显示 {visible.length} / {items.length} 条
        </span>
        {hasFilters && (
          <Button type="link" size="small" className="!h-auto !p-0 text-xs" onClick={clearFilters}>
            清除筛选
          </Button>
        )}
        <span className="ml-auto">Enter 查看详情</span>
      </div>
      {toast && (
        <Alert
          type="success"
          showIcon
          role="status"
          message={toast}
          action={
            undoSteps.length > 0 ? (
              <Button size="small" disabled={busy} onClick={() => void undo()}>
                撤销
              </Button>
            ) : undefined
          }
        />
      )}
      {openItem && (
        <ProposalDetail
          item={openItem}
          items={items}
          draft={session.draft}
          technical={technicalName(openItem, items, session.draft)}
          busy={busy}
          error={proposals.itemErrors[openItem.id]}
          actions={actions}
          onRevise={(candidate, after) =>
            proposals.revise(openItem.id, {
              target_id: candidate.id,
              expected_target_hash: candidate.expected_target_hash,
              after,
            })
          }
          onClose={() => setOpenId(null)}
        />
      )}
      <Modal
        open={confirmReject}
        title={`拒绝全部 ${rejectable.length} 条待审提案？`}
        okText="确认拒绝"
        okButtonProps={{ danger: true, disabled: busy || !rejectable.length }}
        cancelText="取消"
        onCancel={() => setConfirmReject(false)}
        onOk={() => {
          setConfirmReject(false);
          void submit(
            rejectable.map((item) => item.id),
            "reject",
          );
        }}
      >
        <Text>将拒绝全部待审提案（含冲突 / 过期项），不受当前筛选影响。操作后可撤销。</Text>
      </Modal>
    </div>
  );
}
