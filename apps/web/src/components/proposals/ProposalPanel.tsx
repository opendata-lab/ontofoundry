import { X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { ModelingSession, ProposalItem, TargetKind } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { EmptyModel } from "../EmptyModel";
import { ProposalCard, type CardActions } from "./ProposalCard";
import { ProposalDetail } from "./ProposalDetail";
import { EvidencePopover } from "./EvidencePopover";
import { acceptanceBlock, decisionIds, ownerName, reviewKindName, technicalName, type ReviewDecision } from "./reviewMeta";
import { moveFocus, ReviewDialog, ReviewPopover } from "./ReviewOverlays";
import { ReviewIcon } from "./ReviewIcon";

type Props = {
  session: ModelingSession | null;
  proposals: ProposalsState;
  running: boolean;
  onRemodel: (text: string) => void;
};
type StatusFilter = "pending" | "accepted" | "rejected" | "blocked";
type Popover = { kind: "types" | "more"; anchor: HTMLElement } |
  { kind: "evidence"; id: string; anchor: HTMLElement };
const STATUSES: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "待审" }, { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" }, { key: "blocked", label: "冲突" },
];
const KIND_ORDER: TargetKind[] = ["object_type", "property", "link_type", "rule", "value_type", "action", "mapping", "material_object", "material_link"];
const matchesStatus = (item: ProposalItem, status: StatusFilter) => status === "blocked" ?
  ["stale", "conflict"].includes(item.status) : item.status === status;

export function ProposalPanel(props: Props) {
  if (!props.session || (!props.proposals.batches.length && !props.running)) return (
    <div className="proposal-panel proposal-review"><EmptyModel text="向智能体描述场景并开始建模，提案会出现在这里" /></div>
  );
  return <ProposalReview key={`${props.session.id}:${props.proposals.detail?.id ?? "loading"}`} {...props} session={props.session} />;
}

function ProposalReview({ session, proposals, running, onRemodel }: Props & { session: ModelingSession }) {
  const { detail } = proposals;
  const items = useMemo(() => detail?.items ?? [], [detail]);
  const byId = useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const kinds = KIND_ORDER.filter((kind) => items.some((item) => item.target_kind === kind));
  // null denotes all kinds, including kinds first arriving in a refreshed batch.
  const [kindFilter, setKindFilter] = useState<Set<TargetKind> | null>(null);
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(new Set<string>());
  const [openId, setOpenId] = useState<string | null>(null);
  const [popover, setPopover] = useState<Popover | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [toast, setToast] = useState("");
  const [undoSteps, setUndoSteps] = useState<Parameters<ProposalsState["decide"]>[0][]>([]);
  const [undoBusy, setUndoBusy] = useState(false);
  const submitting = useRef(false);
  const busy = proposals.busy || undoBusy;
  const search = useRef<HTMLInputElement>(null);
  const selectVisible = useRef<HTMLInputElement>(null);
  const selectKinds = useRef<HTMLInputElement>(null);
  const more = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const origin = useRef<HTMLElement | null>(null);
  const prefix = useId();
  const listId = `${prefix}-list`;
  const selectedIds = [...selected].filter((id) => byId.has(id));
  const allKinds = kindFilter === null || kinds.every((kind) => kindFilter.has(kind));
  const chosenKinds = kindFilter === null ? kinds : kinds.filter((kind) => kindFilter.has(kind));
  const matchesKind = (item: ProposalItem) => kindFilter === null || kindFilter.has(item.target_kind);
  const matchesSearch = (item: ProposalItem) => {
    const text = [item.display_name, item.before?.name, item.after?.name,
      technicalName(item, items, session.draft), ownerName(item, items, session.draft), item.owner_label]
      .join(" ").toLocaleLowerCase();
    return query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean).every((term) => text.includes(term));
  };
  const visible = items.filter((item) => matchesKind(item) && matchesSearch(item) && matchesStatus(item, status));
  const statusBase = items.filter((item) => matchesKind(item) && matchesSearch(item));
  const kindBase = items.filter((item) => matchesStatus(item, status) && matchesSearch(item));
  const hasConflicts = items.some((item) => matchesStatus(item, "blocked"));
  const statusChoices = STATUSES.filter((tab) => tab.key !== "blocked" || hasConflicts || status === "blocked");
  const acceptable = items.filter((item) => item.status === "pending" && !acceptanceBlock(item, byId));
  const rejectable = items.filter((item) => ["pending", "stale", "conflict"].includes(item.status));
  const selectedVisible = visible.filter((item) => selected.has(item.id)).length;
  const hasFilters = !allKinds || !!query.trim() || status !== "pending";
  // Every decision bumps the session revision, so a moved revision alone is
  // normal; warn only when it actually left proposals stale or conflicting.
  const drifted = !!detail && hasConflicts && detail.source_session_revision !== session.revision;
  const openItem = openId ? byId.get(openId) : undefined;
  const kindLabel = allKinds ? "全部" : !chosenKinds.length ? "未选类型" : chosenKinds.length === 1 ?
    reviewKindName(chosenKinds[0]) : `已选 ${chosenKinds.length} 类`;

  useEffect(() => {
    if (selectVisible.current) selectVisible.current.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
    if (selectKinds.current) selectKinds.current.indeterminate = chosenKinds.length > 0 && !allKinds;
  });
  useEffect(() => {
    if (!toast || undoBusy) return;
    const timer = window.setTimeout(() => setToast(""), 7000);
    return () => window.clearTimeout(timer);
  }, [toast, undoBusy]);

  const resetScroll = () => { if (list.current) list.current.scrollTop = 0; };
  const clearFilters = () => {
    setQuery(""); setKindFilter(null); setStatus("pending"); setPopover(null); resetScroll();
    search.current?.focus({ preventScroll: true });
  };
  const closeDetail = () => {
    setOpenId(null);
    if (origin.current?.isConnected) origin.current.focus({ preventScroll: true });
    else search.current?.focus({ preventScroll: true });
  };
  const submit = async (requested: string[], decision: ReviewDecision, focusSelection = false) => {
    if (busy || submitting.current) return;
    const ids = decisionIds(items, requested, decision);
    if (!ids.length) return;
    const focused = document.activeElement as HTMLElement | null;
    submitting.current = true;
    setPopover(null);
    const ok = await proposals.decide(ids.map((proposal_id) => ({ proposal_id, decision })));
    submitting.current = false;
    if (!ok) return;
    setSelected((current) => new Set([...current].filter((id) => !ids.includes(id))));
    const extra = ids.filter((id) => !requested.includes(id)).length;
    const message = `${{ accept: "已接受", reject: "已拒绝", restore: "已恢复" }[decision]} ${ids.length} 条${extra ? `（含 ${extra} 条依赖项）` : ""}`;
    setAnnouncement(message); setToast(message);
    const step = (values: string[], next: ReviewDecision) => values.map((proposal_id) => ({ proposal_id, decision: next }));
    // Reverse real decisions through the API, never overwrite a local snapshot.
    setUndoSteps(decision === "accept" ? [step(ids, "reject"), step(ids, "restore")] :
      decision === "restore" ? [step(ids, "reject")] :
        [step(ids, "restore"), step(ids.filter((id) => byId.get(id)?.status === "accepted"), "accept")].filter((phase) => phase.length));
    if (focusSelection) selectVisible.current?.focus({ preventScroll: true });
    else if (!openId && focused && !focused.isConnected) search.current?.focus({ preventScroll: true });
  };
  const undo = async () => {
    if (busy || submitting.current || !undoSteps.length) return;
    submitting.current = true;
    setUndoBusy(true); setPopover(null);
    try {
      for (let index = 0; index < undoSteps.length; index++) {
        if (!await proposals.decide(undoSteps[index])) {
          setUndoSteps(undoSteps.slice(index));
          setToast("撤销未完成，请重试");
          return;
        }
      }
      setUndoSteps([]); setToast(""); setAnnouncement("已撤销上次操作");
      selectVisible.current?.focus({ preventScroll: true });
    } finally {
      submitting.current = false;
      setUndoBusy(false);
    }
  };
  const actions: CardActions = {
    accept: (item) => { void submit([item.id], "accept"); },
    reject: (item) => { void submit([item.id], "reject"); },
    restore: (item) => { void submit([item.id], "restore"); },
    open: (item, source) => {
      setPopover(null);
      if (!openId) origin.current = source ?? document.activeElement as HTMLElement;
      setOpenId(item.id);
    },
  };
  const togglePopover = (kind: "types" | "more", anchor: HTMLElement) =>
    setPopover((current) => current?.kind === kind ? null : { kind, anchor });
  const openFromKey = (event: KeyboardEvent<HTMLButtonElement>, kind: "types" | "more") => {
    if (["ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault(); setPopover({ kind, anchor: event.currentTarget });
    }
  };

  return <div className="proposal-panel proposal-review" aria-label="提案审核面板" aria-busy={busy}>
    <div className="panel-tools">
      {running && <p className="proposal-running" role="status">正在生成提案…</p>}
      {drifted && <p className="demo-note" role="status">草稿已更新，部分提案需要重新确认</p>}
      {detail?.status === "failed" && <div className="warning-box" role="alert">提案结果被拒收：{detail.error?.message}
        <button type="button" className="btn quiet" disabled={running || busy} onClick={() => onRemodel("请重新建模并按提案格式输出。")}>重新建模</button>
      </div>}
      {proposals.error && <p className="warning-box" role="alert">{proposals.error}</p>}
    </div>
    <div className="status-tabs" role="tablist" aria-label="审核状态" onKeyDown={(event) => moveFocus(event, "[role=tab]", true)}>
      {statusChoices.map((tab) => {
        const count = statusBase.filter((item) => matchesStatus(item, tab.key)).length;
        return <button type="button" key={tab.key} id={`${prefix}-${tab.key}`} role="tab"
          className={`status-tab${tab.key === "blocked" && count > 0 ? " has-conflicts" : ""}`}
          aria-selected={status === tab.key} aria-controls={listId} tabIndex={status === tab.key ? 0 : -1}
          onClick={() => { setStatus(tab.key); setPopover(null); resetScroll(); }}>
          {tab.label} <span className="filter-count">{count}</span>
        </button>;
      })}
    </div>
    <div className="filter-tools"><div className="search"><ReviewIcon name="search" />
      <input ref={search} type="search" aria-label="搜索提案名称" placeholder="搜索名称、技术名或所属实体…" autoComplete="off"
        value={query} onChange={(event) => { setQuery(event.target.value); setPopover(null); resetScroll(); }} />
      {!!query && <button type="button" className="icon-btn" aria-label="清空搜索" onClick={() => { setQuery(""); setPopover(null); search.current?.focus(); resetScroll(); }}><X /></button>}
    </div>
      <button type="button" className={`btn kind-trigger${allKinds ? "" : " is-filtered"}`}
        aria-haspopup="dialog" aria-expanded={popover?.kind === "types"} aria-controls={`${prefix}-kinds`}
        title={allKinds ? "类型：全部" : chosenKinds.length ? `类型：${chosenKinds.map((kind) => reviewKindName(kind)).join("、")}` : "请选择要显示的元素类型"}
        onClick={(event) => togglePopover("types", event.currentTarget)} onKeyDown={(event) => openFromKey(event, "types")}>
        <span className="filter-label">类型：</span><span>{kindLabel}</span><ReviewIcon name="chevron" />
      </button>
      {popover?.kind === "types" && <ReviewPopover anchor={popover.anchor} className="kind-menu" id={`${prefix}-kinds`} label="元素类型" onClose={() => setPopover(null)}>
        <header className="kind-menu-heading"><h3>元素类型</h3><span>可多选</span></header>
        <div role="group" aria-label="选择元素类型">
          <label className="kind-option kind-option-all"><input ref={selectKinds} type="checkbox" checked={allKinds}
            onChange={(event) => { setKindFilter(event.target.checked ? null : new Set()); resetScroll(); }} /><span>全部</span><span className="filter-count">{kindBase.length}</span></label>
          {kinds.map((kind) => <label className="kind-option" key={kind}><input type="checkbox" checked={kindFilter === null || kindFilter.has(kind)}
            onChange={(event) => { const next = new Set(chosenKinds); if (event.target.checked) next.add(kind); else next.delete(kind); setKindFilter(next); resetScroll(); }} />
            <span>{reviewKindName(kind)}</span><span className="filter-count">{kindBase.filter((item) => item.target_kind === kind).length}</span>
          </label>)}
        </div>
      </ReviewPopover>}
    </div>
    <div className={`selection-bar${selectedIds.length ? " has-selection" : ""}`}>
      <label className="selection-label" title={selectedIds.length ? `共选 ${selectedIds.length} 项，当前结果中 ${selectedVisible} 项` : undefined}>
        <input ref={selectVisible} type="checkbox" aria-label="选择当前筛选的全部提案" disabled={!visible.length}
          checked={visible.length > 0 && selectedVisible === visible.length} onChange={(event) => {
            const checked = event.target.checked;
            setSelected((current) => { const next = new Set(current); for (const item of visible) { if (checked) next.add(item.id); else next.delete(item.id); } return next; });
          }} /><span>{selectedIds.length ? `已选 ${selectedIds.length} 项` : "选择当前结果"}</span>
      </label>
      <div className="selection-buttons" role="group" aria-label="批量审核操作">
        {selectedIds.length ? <><span className="selection-divider" aria-hidden="true">·</span>
          <button type="button" className="btn quiet" disabled={busy || !selectedIds.some((id) => byId.get(id)?.status === "pending" && !acceptanceBlock(byId.get(id)!, byId))}
            onClick={() => { void submit(selectedIds, "accept", true); }}>接受选中</button>
          <button type="button" className="btn quiet selected-reject" disabled={busy || !decisionIds(items, selectedIds, "reject").length}
            onClick={() => { void submit(selectedIds, "reject", true); }}>拒绝选中</button>
          <button type="button" className="btn quiet" onClick={() => { setSelected(new Set()); selectVisible.current?.focus({ preventScroll: true }); }}>取消选择</button>
        </> : <span title={acceptable.length ? "接受全部可接受且无冲突的待审提案，不受当前筛选影响" : "没有可接受的无冲突待审提案"} tabIndex={acceptable.length ? -1 : 0}>
          <button type="button" className="btn bulk-accept" disabled={busy || !acceptable.length}
            onClick={() => { void submit(acceptable.map((item) => item.id), "accept", true); }}>全部接受（{acceptable.length}）</button>
        </span>}
        <button ref={more} type="button" className="btn quiet more-button" aria-haspopup="menu" aria-expanded={popover?.kind === "more"}
          aria-controls={`${prefix}-more`} onClick={(event) => togglePopover("more", event.currentTarget)}
          onKeyDown={(event) => openFromKey(event, "more")}>⋯ 更多</button>
        {popover?.kind === "more" && <ReviewPopover className="bulk-menu" anchor={popover.anchor} id={`${prefix}-more`} label="更多批量操作" role="menu" onClose={() => setPopover(null)}>
          <p>作用于全部待审提案</p><button type="button" role="menuitem" disabled={busy || !rejectable.length}
            onClick={() => { setPopover(null); setConfirmReject(true); }}>全部拒绝</button>
        </ReviewPopover>}
      </div>
    </div>
    <div ref={list} id={listId} className="proposal-list" role="tabpanel" aria-labelledby={`${prefix}-${status}`} tabIndex={0}
      onScroll={() => { if (popover?.kind === "evidence") setPopover(null); }}>
      {visible.length ? visible.map((item) => <ProposalCard key={item.id} item={item} technical={technicalName(item, items, session.draft)}
        busy={busy} error={proposals.itemErrors[item.id]} blocked={acceptanceBlock(item, byId)} actions={actions}
        selected={selected.has(item.id)} onSelect={(checked) => setSelected((current) => { const next = new Set(current); if (checked) next.add(item.id); else next.delete(item.id); return next; })}
        evidenceOpen={popover?.kind === "evidence" && popover.id === item.id}
        onEvidence={(anchor) => setPopover((current) => current?.kind === "evidence" && current.id === item.id ? null : { kind: "evidence", id: item.id, anchor })} />) :
        <div className="empty"><strong>{hasFilters ? "没有符合条件的提案" : "当前没有待审提案"}</strong>
          <span>{hasFilters ? "试试其他类型、状态或名称。" : "切换状态页签，查看已审核的提案。"}</span>
          {hasFilters && <button type="button" className="btn" onClick={clearFilters}>清除筛选</button>}
        </div>}
    </div>
    <footer className="panel-footer"><div className="result-summary"><span>显示 {visible.length} / {items.length} 条</span>
      {hasFilters && <span>· <button type="button" className="clear-filters" title="清空搜索和类型筛选，返回待审" onClick={clearFilters}>清除筛选</button></span>}
    </div><span><kbd>Enter</kbd> 详情 · 证据图标查看来源</span></footer>
    {popover?.kind === "evidence" && byId.has(popover.id) && <EvidencePopover anchor={popover.anchor}
      evidence={byId.get(popover.id)!.evidence} onClose={() => setPopover(null)} />}
    {openItem && <ProposalDetail item={openItem} items={items} technical={technicalName(openItem, items, session.draft)}
      busy={busy} error={proposals.itemErrors[openItem.id]} actions={actions} onClose={closeDetail} />}
    {confirmReject && <ReviewDialog className="confirm-dialog" label={`拒绝全部 ${rejectable.length} 条待审提案？`}
      onClose={() => { setConfirmReject(false); more.current?.focus({ preventScroll: true }); }}>
      <header className="modal-header"><div><h2>拒绝全部 {rejectable.length} 条待审提案？</h2></div>
        <button type="button" className="icon-btn" aria-label="关闭拒绝全部确认" onClick={() => { setConfirmReject(false); more.current?.focus(); }}><X /></button>
      </header><div className="modal-body"><p>将拒绝全部待审提案（含冲突 / 过期项），不受当前筛选影响。操作后可撤销。</p></div>
      <footer className="modal-footer"><div className="actions">
        <button type="button" className="btn" data-initial-focus onClick={() => { setConfirmReject(false); more.current?.focus(); }}>取消</button>
        <button type="button" className="btn destructive" disabled={busy || !rejectable.length}
          onClick={() => { setConfirmReject(false); more.current?.focus(); void submit(rejectable.map((item) => item.id), "reject"); }}>确认拒绝</button>
      </div></footer>
    </ReviewDialog>}
    {toast && <div className="toast"><span>{toast}</span>{undoSteps.length > 0 && <button type="button" disabled={busy} onClick={() => { void undo(); }}>撤销</button>}</div>}
    <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
  </div>;
}
