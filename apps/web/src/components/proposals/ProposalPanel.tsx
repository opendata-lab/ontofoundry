import { Alert, Button, Checkbox, Dropdown, Empty, Flex, Input, Modal, Select, Spin, Tabs, Tooltip, Typography } from "antd";
import { MoreHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ModelingSession, ProposalItem, TargetKind } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { ImportReportDialog } from "../ImportReportDialog";
import { PanelToolbar } from "../layout";
import { ProposalCard, type CardActions } from "./ProposalCard";
import { ProposalDetail } from "./ProposalDetail";
import { acceptanceBlock, decisionIds, reviewKindName, searchText, technicalName, type ReviewDecision } from "./reviewMeta";

const { Text } = Typography;

type Props = {
  session: ModelingSession | null;
  proposals: ProposalsState;
  running: boolean;
  /** The session is still loading. */
  loading?: boolean;
  onRemodel: (text: string) => void;
};
type StatusFilter = "pending" | "accepted" | "rejected" | "blocked" | "unacceptable";
const STATUSES: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "待审" },
  { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" },
  { key: "blocked", label: "冲突" },
  { key: "unacceptable", label: "不可接受" },
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

// The latest modeling run's outcome belongs to the proposals it was meant to
// produce, so a run that produced none says why here, not in the conversation.
const failedRun = (session: ModelingSession | null | undefined) =>
  session?.result_state === "failed_permanent" ? session.task_detail || "本轮没有产出提案" : "";

export function ProposalPanel(props: Props) {
  if (props.loading || (props.proposals.loading && !props.proposals.batches.length))
    return (
      <Flex vertical align="center" gap="small" className="p-6" role="status">
        <Spin />
        <Text type="secondary">正在加载提案…</Text>
      </Flex>
    );
  if (props.session && props.running && !props.proposals.batches.length)
    return (
      <Flex vertical align="center" gap="small" className="p-6" role="status">
        <Spin />
        <Text type="secondary">正在生成提案…</Text>
      </Flex>
    );
  if (!props.session || (!props.proposals.batches.length && !props.running))
    return <Empty className="m-0 p-6" description={failedRun(props.session) || "向智能体描述场景并开始建模，提案会出现在这里"} />;
  return (
    <ProposalReview key={`${props.session.id}:${props.proposals.detail?.id ?? "loading"}`} {...props} session={props.session} />
  );
}

function ProposalReview({ session, proposals, running, onRemodel }: Props & { session: ModelingSession }) {
  const { detail } = proposals;
  const [reportOpen, setReportOpen] = useState(false);
  const producer = detail?.producer;
  const importSource = producer?.kind === "import" && producer.adapter && producer.report_id ? { adapter: producer.adapter, report_id: producer.report_id } : session.import_source;
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
  const statusChoices = STATUSES.filter((tab) =>
    tab.key === "blocked" ? hasConflicts || status === "blocked" :
    tab.key === "unacceptable" ? items.some((item) => item.status === "unacceptable") : true);
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
    <div className="flex h-full min-h-0 flex-col" aria-label="提案审核面板" aria-busy={busy}>
      {importSource && <>
        <PanelToolbar><Typography.Text type="secondary">文件导入 · {importSource.adapter}</Typography.Text><Button size="small" onClick={() => setReportOpen(true)}>查看导入报告与补全</Button></PanelToolbar>
        <ImportReportDialog open={reportOpen} source={importSource} session={session} onClose={() => setReportOpen(false)} onChanged={(result) => { proposals.select(result.batch_id); proposals.reload(); }} />
      </>}
      {running && <Alert type="info" showIcon message="正在生成提案…" />}
      {!running && failedRun(session) && <Alert type="error" showIcon message={failedRun(session)} />}
      {drifted && <Alert type="warning" showIcon message="草稿已更新，部分提案需要重新确认" />}
      {proposals.error && <Alert type="error" showIcon message={proposals.error} />}
      <Tabs
        size="small"
        activeKey={status}
        onChange={(value) => setStatus(value as StatusFilter)}
        renderTabBar={(props, DefaultTabBar) => <PanelToolbar tabBar={<DefaultTabBar {...props} />} />}
        items={statusChoices.map((tab) => {
          const count = statusBase.filter((item) => matchesStatus(item, tab.key)).length;
          const alert = tab.key === "blocked" && count > 0;
          return {
            key: tab.key,
            label: (
              <span className={`text-xs ${alert ? "text-danger" : ""}`}>
                {tab.label}
                <span className={`ml-1 tabular-nums ${alert ? "text-danger" : "text-muted"}`}>{count}</span>
              </span>
            ),
          };
        })}
      />
      <div className="flex items-center gap-2 border-b border-rule px-4 py-2">
        <Input.Search
          allowClear
          size="small"
          aria-label="搜索提案名称"
          placeholder="搜索名称、英文标识或所属对象…"
          className="min-w-0 flex-1"
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
          className="min-w-review-filter"
          value={kindFilter}
          onChange={setKindFilter}
          options={kinds.map((kind) => ({
            value: kind,
            label: `${reviewKindName(kind)} ${items.filter((i) => i.target_kind === kind && matchesStatus(i, status)).length}`,
          }))}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-4 py-2">
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
      <div className="relative min-h-0 flex-1 overflow-auto" role="list" aria-busy={proposals.loading}>
        {proposals.loading && (
          <div className="absolute inset-0 z-10 flex justify-center bg-surface/60 pt-8" role="status" aria-label="正在加载提案">
            <Spin />
          </div>
        )}
        {visible.length || proposals.loading ? (
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
          <Empty className="py-6" description={hasFilters ? "没有符合条件的提案" : "当前没有待审提案"}>
            {hasFilters && <Button onClick={clearFilters}>清除筛选</Button>}
          </Empty>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-rule bg-surface-raised px-4 py-2 text-xs text-muted">
        <span>
          显示 {visible.length} / {items.length} 条
        </span>
        {hasFilters && (
          <Button type="link" size="small" className="h-auto p-0 text-xs" onClick={clearFilters}>
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
          workspaceId={session.workspace_id}
          onReviseDataset={(dataset) => proposals.reviseDataset(openItem.id, dataset)}
          onReviseContent={(fields) => proposals.reviseContent(openItem.id, fields)}
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
