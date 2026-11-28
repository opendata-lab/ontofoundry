import { Alert, Button, Checkbox, Dropdown, Empty, Flex, Input, Modal, Spin, Tabs, Tooltip, Typography } from "antd";
import { ChevronDown, ChevronRight, MoreHorizontal } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Draft, ModelingSession, ProposalItem, TargetKind } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { byId } from "../../lib/coreModel";
import { ELEMENT_CATEGORIES, type ElementCategory } from "../../lib/elementCategories";
import { ElementCategoryTiles } from "../ElementCategoryTiles";
import { ImportReportDialog } from "../ImportReportDialog";
import { PanelToolbar } from "../layout";
import { ProposalCard, type CardActions } from "./ProposalCard";
import { ProposalDetail } from "./ProposalDetail";
import { acceptanceBlock, decisionIds, searchText, technicalName, type ReviewDecision } from "./reviewMeta";

const { Text } = Typography;

type Props = {
  session: ModelingSession | null;
  proposals: ProposalsState;
  running: boolean;
  /** The session is still loading. */
  loading?: boolean;
  canEdit?: boolean;
};
type StatusFilter = "pending" | "incomplete" | "accepted" | "rejected";
const STATUSES: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "待审" },
  { key: "incomplete", label: "待补全" },
  { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" },
];
// 待补全 is the part of 待审 that cannot be accepted until it is completed.
const matchesStatus = (item: ProposalItem, status: StatusFilter) =>
  status === "incomplete"
    ? item.status === "pending" && !!item.acceptance_issues?.length
    : item.status === status;

// The latest modeling run's outcome belongs to the proposals it was meant to
// produce, so a run that produced none says why here, not in the conversation.
const failedRun = (session: ModelingSession | null | undefined) =>
  session?.result_state === "failed_permanent" ? session.task_detail || "本轮没有产出提案" : "";

type ProposalGroup =
  | { type: "object"; key: string; title: string; changed: boolean; objects: ProposalItem[]; properties: ProposalItem[] }
  | { type: "kind"; key: string; title: string; tone: string; members: ProposalItem[] };

const elementField = (item: ProposalItem, key: string) => {
  const value = (item.after ?? item.before) as unknown as Record<string, unknown> | null;
  return value?.[key];
};

/** The object an object or property proposal belongs to: its own target, or the property's owner. */
const ownerOf = (item: ProposalItem) =>
  item.target_kind === "object_type" ? item.target_id : (elementField(item, "owner_type_id") as string | undefined) ?? item.owner_label ?? "";

function ownerTitle(id: string, items: ProposalItem[], draft: Draft, fallback: string) {
  const proposal = items.find((candidate) => candidate.target_kind === "object_type" && candidate.target_id === id);
  if (proposal) return String(elementField(proposal, "display_name") || proposal.display_name || elementField(proposal, "name") || fallback);
  const existing = byId(draft.object_types, id);
  return existing?.display_name || existing?.name || fallback || "未知对象";
}

function proposalGroups(visible: ProposalItem[], others: ElementCategory[], items: ProposalItem[], draft: Draft): ProposalGroup[] {
  const byOwner = new Map<string, { objects: ProposalItem[]; properties: ProposalItem[] }>();
  for (const item of visible) {
    if (item.target_kind !== "object_type" && item.target_kind !== "property") continue;
    const owner = ownerOf(item);
    const entry = byOwner.get(owner) ?? { objects: [], properties: [] };
    (item.target_kind === "object_type" ? entry.objects : entry.properties).push(item);
    byOwner.set(owner, entry);
  }
  const objectGroups: ProposalGroup[] = [...byOwner].map(([owner, entry]) => ({
    type: "object",
    key: `object:${owner}`,
    title: ownerTitle(owner, items, draft, entry.properties.find((m) => m.owner_label)?.owner_label ?? ""),
    // The batch also changes the object itself, even when a filter hides that card.
    changed: items.some((candidate) => candidate.target_kind === "object_type" && candidate.target_id === owner),
    ...entry,
  }));
  const kindGroups: ProposalGroup[] = others
    .filter((category) => category.key !== "object_type" && category.key !== "property")
    .map((category) => ({ type: "kind" as const, key: category.key, title: category.text, tone: category.tone, members: visible.filter((item) => item.target_kind === category.key) }))
    .filter((group) => group.members.length);
  return [...objectGroups, ...kindGroups];
}

export function ProposalPanel(props: Props) {
  if (props.loading || (props.proposals.loading && !props.proposals.batches.length))
    return (
      <Flex vertical align="center" gap="small" className="p-6" role="status">
        <Spin />
        <Text type="secondary">正在加载提案…</Text>
      </Flex>
    );
  if (props.proposals.error && !props.proposals.batches.length)
    return (
      <Flex vertical gap="small" className="p-6">
        <Alert type="error" showIcon message={props.proposals.error} />
        <Button size="small" className="self-start" onClick={props.proposals.reload}>重新加载</Button>
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

function ProposalReview({ session, proposals, running, canEdit = true }: Props & { session: ModelingSession }) {
  const { detail } = proposals;
  const [reportOpen, setReportOpen] = useState(false);
  const producer = detail?.producer;
  const importSource = producer?.kind === "import" && producer.adapter && producer.report_id ? { adapter: producer.adapter, report_id: producer.report_id } : session.import_source;
  // Superseded items were folded into a newer batch; their history is in the change log.
  const items = useMemo(() => (detail?.items ?? []).filter((item) => item.status !== "superseded"), [detail]);
  const byId = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const categories = ELEMENT_CATEGORIES.filter((category) => items.some((item) => item.target_kind === category.key));
  const [kind, setKind] = useState<TargetKind | null>(null);
  // Groups the reviewer flipped from their default: kind groups stay keyed by kind across
  // queries, while object groups scope flips per view (all / property / search).
  const [toggled, setToggled] = useState(new Set<string>());
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(new Set<string>());
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);
  const [toast, setToast] = useState("");
  const [undoSteps, setUndoSteps] = useState<Parameters<ProposalsState["decide"]>[0][]>([]);
  const [undoBusy, setUndoBusy] = useState(false);
  const submitting = useRef(false);
  const busy = proposals.busy || undoBusy || running || !!detail?.read_only;
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matchesKind = (item: ProposalItem) => !kind || item.target_kind === kind;
  const matchesSearch = (item: ProposalItem) => {
    if (!terms.length) return true;
    const text = searchText(item, items, session.draft);
    return terms.every((term) => text.includes(term));
  };
  const visible = items.filter((item) => matchesKind(item) && matchesSearch(item) && matchesStatus(item, status));
  const statusBase = items.filter((item) => matchesKind(item) && matchesSearch(item));
  const statusChoices = STATUSES;
  const acceptable = items.filter((item) => item.status === "pending" && !acceptanceBlock(item, byId));
  const rejectable = items.filter((item) => item.status === "pending");
  const selectedIds = [...selected].filter((id) => byId.has(id));
  const selectedVisible = visible.filter((item) => selected.has(item.id)).length;
  const hasFilters = !!kind || !!terms.length || status !== "pending";
  // Under 全部 and 属性, each object is a group holding its own proposal and its
  // properties; the other kinds follow as one group per kind, in tile order.
  const groups = kind && kind !== "property" ? null : proposalGroups(visible, kind ? [] : categories, items, session.draft);
  const objectFoldView = terms.length > 0 ? "search" : kind === "property" ? "property" : "all";
  const foldKey = (group: ProposalGroup) => (group.type === "object" ? `${objectFoldView}:${group.key}` : group.key);
  // A search opens objects too, so a matching property is never hidden behind a closed object.
  const isOpen = (group: ProposalGroup) => (group.type === "object" ? objectFoldView !== "all" : true) !== toggled.has(foldKey(group));
  const flip = (group: ProposalGroup) => {
    const key = foldKey(group);
    setToggled((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  const openItem = openId ? byId.get(openId) : undefined;
  useEffect(() => {
    if (!toast || undoBusy) return;
    const timer = window.setTimeout(() => setToast(""), 7000);
    return () => window.clearTimeout(timer);
  }, [toast, undoBusy]);
  const clearFilters = () => {
    setQuery("");
    setKind(null);
    setStatus("pending");
  };
  const submit = async (requested: string[], decision: ReviewDecision, partial = false) => {
    if (busy || submitting.current) return;
    const ids = decisionIds(items, requested, decision);
    if (!ids.length) return;
    submitting.current = true;
    const decisions = ids.map((proposal_id) => ({ proposal_id, decision }));
    const result = await (partial ? proposals.decide(decisions, true) : proposals.decide(decisions));
    submitting.current = false;
    if (!result) return;
    // An "accept all" leaves what did not pass pending, with the reason.
    const setAside = partial ? result.results.filter((r) => r.status === "pending") : [];
    // The server may have reached further (other batches, later changes): use what it changed.
    const changed = result.results.filter((r) => !setAside.includes(r)).map((r) => r.proposal_id);
    setSelected((current) => new Set([...current].filter((id) => !changed.includes(id))));
    const verb = { accept: "已接受", reject: "已拒绝", restore: "已恢复", back_to_pending: "已退回待审" }[decision];
    const extra = changed.filter((id) => !requested.includes(id));
    const acceptedCount = partial ? changed.length : requested.length;
    const names = extra.map((id) => byId.get(id)?.display_name ?? id).slice(0, 5);
    const also = { accept: "同时接受了", reject: "同时撤销了", restore: "同时恢复了", back_to_pending: "同时退回待审" }[decision];
    // Rules the platform could not evaluate on these instances (AC-07); a note, not a refusal.
    const unchecked = (result.validation?.warnings ?? []).filter((w) => w.code === "RULE_NOT_CHECKED").map((w) => w.message);
    setToast(
      (partial
        ? `${verb} ${acceptedCount} 条`
        : `${verb} ${requested.length} 条${extra.length ? `；${also}：${names.join("、")}${extra.length > names.length ? ` 等 ${extra.length} 条` : ""}` : ""}`) +
        (setAside.length
          ? `；${setAside.length} 条未通过，仍待审：${setAside.slice(0, 3).map((r) => `${byId.get(r.proposal_id)?.display_name ?? r.proposal_id}（${r.reason}）`).join("；")}${setAside.length > 3 ? ` 等` : ""}`
          : "") +
        (unchecked.length ? `。${unchecked.slice(0, 3).join("；")}${unchecked.length > 3 ? ` 等 ${unchecked.length} 条` : ""}` : ""),
    );
    const step = (values: string[], next: ReviewDecision) => values.map((proposal_id) => ({ proposal_id, decision: next }));
    const wasAccepted = changed.filter((id) => byId.get(id)?.status === "accepted");
    // Reverse real decisions through the API, never overwrite a local snapshot.
    setUndoSteps(
      decision === "accept"
        ? [step(changed, "reject"), step(changed, "restore")]
        : decision === "restore"
          ? [step(changed, "reject")]
          : decision === "back_to_pending"
            ? [step(changed, "accept")]
            : [step(changed, "restore"), step(wasAccepted, "accept")].filter((phase) => phase.length),
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
    backToPending: (item) => void submit([item.id], "back_to_pending"),
    open: (item) => setOpenId(item.id),
  };
  const toggle = (id: string, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  const renderCard = (item: ProposalItem) => (
    <ProposalCard
      key={item.id}
      item={item}
      items={items}
      technical={technicalName(item, items, session.draft)}
      busy={busy}
      canEdit={canEdit}
      error={proposals.itemErrors[item.id]}
      blocked={acceptanceBlock(item, byId)}
      actions={actions}
      selected={selected.has(item.id)}
      onSelect={(checked) => toggle(item.id, checked)}
    />
  );
  return (
    <div className="flex h-full min-h-0 flex-col" aria-label="提案审核面板" aria-busy={busy}>
      {importSource && <>
        <PanelToolbar><Typography.Text type="secondary">文件导入 · {importSource.adapter}</Typography.Text>{canEdit && <Button size="small" onClick={() => setReportOpen(true)}>查看导入报告与补全</Button>}</PanelToolbar>
        {canEdit && <ImportReportDialog open={reportOpen} source={importSource} session={session} onClose={() => setReportOpen(false)} onChanged={(result) => { proposals.select(result.batch_id); proposals.reload(); }} />}
      </>}
      {running && <Alert type="info" showIcon message="正在生成提案…" />}
      {!running && failedRun(session) && <Alert type="error" showIcon message={failedRun(session)} />}
      {detail?.read_only && <Alert type="info" showIcon message="新一轮已开始，此批次只读" />}
      {proposals.error && <Alert type="error" showIcon message={proposals.error} />}
      <Tabs
        size="small"
        activeKey={status}
        onChange={(value) => setStatus(value as StatusFilter)}
        renderTabBar={(props, DefaultTabBar) => <PanelToolbar tabBar={<DefaultTabBar {...props} />} />}
        items={statusChoices.map((tab) => {
          const count = statusBase.filter((item) => matchesStatus(item, tab.key)).length;
          const alert = tab.key === "incomplete" && count > 0;
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
      <div className="flex flex-col gap-2 border-b border-rule px-4 py-2">
        <ElementCategoryTiles
          label="提案分类"
          categories={categories}
          count={(k) => items.filter((i) => i.target_kind === k && matchesStatus(i, status) && matchesSearch(i)).length}
          allTotal={items.filter((i) => matchesStatus(i, status) && matchesSearch(i)).length}
          selected={kind}
          onSelect={setKind}
        />
        <Input.Search
          allowClear
          size="small"
          aria-label="搜索提案名称"
          placeholder="搜索名称、英文标识或所属对象…"
          className="min-w-0"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {canEdit && (
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
              <Tooltip title={acceptable.length ? "接受全部待审提案及其依赖，不受当前筛选影响" : "没有待审提案"}>
                <span className="inline-flex">
                  <Button
                    size="small"
                    type="primary"
                    disabled={busy || !acceptable.length}
                    onClick={() => void submit(acceptable.map((item) => item.id), "accept", true)}
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
      )}
      <div className="relative min-h-0 flex-1 overflow-auto" role="list" aria-busy={proposals.loading}>
        {proposals.loading && (
          <div className="absolute inset-0 z-10 flex justify-center bg-surface/60 pt-8" role="status" aria-label="正在加载提案">
            <Spin />
          </div>
        )}
        {visible.length || proposals.loading ? (
          groups ? (
            groups.map((group) => {
              const open = isOpen(group);
              if (group.type === "kind")
                return (
                  <section key={group.key} aria-label={`${group.title}提案`}>
                    <button type="button" aria-expanded={open} onClick={() => flip(group)}
                      className="sticky top-0 z-1 flex w-full items-center gap-2 border-b border-rule bg-surface-raised px-4 py-1.5 text-left text-xs font-semibold text-ink-2">
                      {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span className={group.tone}>{group.title}</span>
                      <span className="tabular-nums text-muted">{group.members.length}</span>
                    </button>
                    {open && group.members.map(renderCard)}
                  </section>
                );
              const toggle = group.properties.length > 0 && (
                <button type="button" aria-expanded={open} onClick={() => flip(group)}
                  aria-label={`${open ? "收起" : "展开"} ${group.title} 的属性（${group.properties.length}）`}
                  className="flex w-full items-center gap-1.5 border-b border-rule-soft bg-surface px-4 py-1 pl-10 text-left text-xs text-ink-2 hover:bg-surface-soft">
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  属性 <span className="tabular-nums">{group.properties.length}</span>
                </button>
              );
              return (
                <section key={group.key} aria-label={`${group.title}提案`}>
                  {group.objects.length ? (
                    group.objects.map(renderCard)
                  ) : (
                    // Properties of an object this batch leaves unchanged still need a parent row.
                    <div className="flex items-center gap-2 border-b border-rule-soft bg-surface-raised px-4 py-2 text-xs">
                      <span className="font-semibold text-object">{group.title}</span>
                      {!group.changed && <span className="text-muted">已有对象，本批未修改</span>}
                    </div>
                  )}
                  {toggle}
                  {open && group.properties.length > 0 && (
                    <div className="ml-6 border-l-2 border-rule">{group.properties.map(renderCard)}</div>
                  )}
                </section>
              );
            })
          ) : (
            visible.map(renderCard)
          )
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
          canEdit={canEdit}
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
          sessionId={session.id}
          sessionRevision={session.revision}
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
        <Text>将拒绝全部待审提案及其依赖项，不受当前筛选影响。新一轮开始前可撤销。</Text>
      </Modal>
    </div>
  );
}
