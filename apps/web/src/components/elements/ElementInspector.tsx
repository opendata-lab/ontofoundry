import { Alert, Button, Input, List, Modal, Spin, Tabs, Tag, Tooltip, Typography } from "antd";
import { Box, Check, Database, GitBranch, Maximize2, Minimize2, Sigma } from "lucide-react";
import { useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { createPath, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, modelingApi, publishApi } from "../../api/client";
import {
  COLLECTION_BY_KIND,
  type AffectedItem,
  type Dataset,
  type Draft,
  type ElementSave,
  type ElementSaveImpact,
  type LinkType,
  type Metric,
  type ModelingSession,
  type ObjectType,
} from "../../api/types";
import { PageTabContext, usePageActive } from "../../hooks/usePageTab";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { byId, effectiveProperties, mappingFor, upsert } from "../../lib/coreModel";
import { branchProblem } from "../../lib/derivedEditing";
import {
  inspectorHref,
  notifyOntologySaved,
  withoutInspector,
  type ElementRequest,
  type ElementTab,
} from "../../lib/elementInspector";
import { relationsFor, rulesFor, type PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { documentDisplayText } from "../../lib/instanceDisplay";
import { metricErrors, newMetric, storedMetric } from "../../lib/metricEditing";
import { objectMapping, shortObjectName } from "../../lib/objectMapping";
import { newDataset } from "../../lib/datasetEditing";
import { KIND } from "../proposals/elementMeta";
import { DatasetPanel } from "./DatasetPanel";
import { ElementInstances } from "./ElementInstances";
import { LinkBasicPanel, ObjectBasicPanel, RulesPanel } from "./ElementPanels";
import { InspectorDialog } from "./InspectorDialog";
import { joinProblem } from "../../lib/objectMappingEditing";
import { LinkMappingPanel } from "./LinkMappingPanel";
import { MappingStatusIcon } from "./MappingWidgets";
import { MetricPanel } from "./MetricPanel";
import { PropertiesPanel } from "./PropertyMappingTable";
import { RelationsPanel } from "./RelationMappingTable";

const { Text } = Typography;

type InspectKind = "object_type" | "link_type" | "metric" | "dataset";
type Element = ObjectType | LinkType | Metric | Dataset;
type Loaded = { draft: Draft; session: ModelingSession | null; versionId: string | null };
type Resolved = { kind: InspectKind; element: Element | undefined; tab?: ElementTab; factId?: string };
type ImpactPreview = {
  candidate: ElementSave;
  signature: string;
  items: ElementSaveImpact["affected_items"];
};

const KINDS = new Set([
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
  "mapping",
  "material_object",
  "material_link",
]);
const NEW_KINDS: InspectKind[] = ["object_type", "link_type", "metric", "dataset"];
const COLLECTION = { object_type: "object_types", link_type: "link_types", metric: "metrics", dataset: "datasets" } as const;
const NOUN: Record<InspectKind, string> = { object_type: "对象", link_type: "关系", metric: "指标", dataset: "数据集" };

/** Opens the owning resource for a nested element (property, rule, mapping, fact). */
function resolve(draft: Draft, kind: string, id: string): Resolved {
  switch (kind) {
    case "object_type":
    case "link_type":
    case "metric":
    case "dataset":
      return { kind, element: byId(draft[COLLECTION[kind]] as Element[], id) };
    case "property":
      return {
        kind: "object_type",
        element: byId(draft.object_types, byId(draft.properties, id)?.owner_type_id),
        tab: "properties",
      };
    case "mapping":
      return {
        kind: "object_type",
        element: byId(draft.object_types, byId(draft.mappings, id)?.type_id),
        tab: "properties",
      };
    case "material_object": {
      const fact = byId(draft.material_objects, id);
      return { kind: "object_type", element: byId(draft.object_types, fact?.type_id), tab: "instances", factId: fact?.id };
    }
    case "material_link":
      return {
        kind: "link_type",
        element: byId(draft.link_types, byId(draft.material_links, id)?.type_id),
        tab: "instances",
      };
    case "rule": {
      const rule = byId(draft.rules, id);
      if (!rule) return { kind: "object_type", element: undefined };
      const owner = rule.owner_kind === "property" ? byId(draft.properties, rule.owner_id)?.owner_type_id : rule.owner_id;
      return rule.owner_kind === "link_type"
        ? { kind: "link_type", element: byId(draft.link_types, owner), tab: "rules" }
        : { kind: "object_type", element: byId(draft.object_types, owner), tab: "rules" };
    }
    default:
      return { kind: "object_type", element: undefined };
  }
}

function blank(draft: Draft, kind: InspectKind, id: string, owner: string | null): Element {
  const base = { id, name: "", technical_name: "", description: "", synonyms: [], evidence: [] };
  if (kind === "object_type")
    return { ...base, tags: [], extends: null, derived_by: [], title_property_id: null };
  if (kind === "link_type") {
    const source = byId(draft.object_types, owner)?.id ?? draft.object_types[0]?.id ?? "";
    return {
      ...base,
      tags: [],
      source_type_id: source,
      target_type_id: draft.object_types.find((o) => o.id !== source)?.id ?? source,
      multiplicity: "many_to_one",
      inverse_name: null,
      data_join: null,
    };
  }
  if (kind === "metric") return newMetric(id, byId(draft.datasets, owner)?.id ?? draft.datasets[0]?.id ?? null);
  return newDataset(id);
}

/** First problem to fix before saving, or null. */
function saveProblem(draft: Draft, kind: InspectKind, element: Element): string | null {
  if (kind === "dataset") {
    const dataset = element as Dataset;
    if (!dataset.name.trim()) return "请填写数据集名称";
    return dataset.table_name ? null : "请填写表或视图";
  }
  if (kind === "metric") return Object.values(metricErrors(draft, element as Metric))[0] ?? null;
  const named = element as ObjectType | LinkType;
  if (!named.name.trim() || !named.technical_name) return `请填写${NOUN[kind]}的名称和技术名`;
  if (rulesFor(draft, named).some((r) => !r.name.trim() || !r.technical_name || !r.expression.trim()))
    return "有规则还没有填写名称、技术名和表达式";
  if (kind === "link_type") return joinProblem((element as LinkType).data_join);
  const object = element as ObjectType;
  const unnamed = draft.properties.find((p) => p.owner_type_id === object.id && (!p.name.trim() || !p.technical_name));
  if (unnamed) return "有属性还没有填写名称和技术名";
  const derived = branchProblem(draft, object.derived_by);
  if (derived) return derived;
  for (const join of Object.values(mappingFor(draft, object.id)?.inherited_link_bindings ?? {})) {
    const problem = joinProblem(join);
    if (problem) return problem;
  }
  return null;
}

function affectedElementName(
  draft: Draft,
  base: Draft,
  item: Pick<AffectedItem, "target_kind" | "target_id">,
): string {
  const { target_kind: kind, target_id: id } = item;
  switch (kind) {
    case "object_type":
    case "property":
    case "link_type":
    case "rule":
    case "metric":
    case "dataset": {
      const collection = COLLECTION_BY_KIND[kind];
      const found =
        byId(draft[collection] as { id: string; name?: string }[], id) ??
        byId(base[collection] as { id: string; name?: string }[], id);
      return found?.name?.trim() || id;
    }
    case "mapping": {
      const mapping = byId(draft.mappings, id) ?? byId(base.mappings, id);
      const owner = mapping
        ? (byId(draft.object_types, mapping.type_id) ?? byId(base.object_types, mapping.type_id))
        : undefined;
      return owner?.name?.trim() || id;
    }
    case "material_object": {
      const baseFact = byId(base.material_objects, id);
      if (baseFact) return documentDisplayText(base, baseFact);
      const fact = byId(draft.material_objects, id);
      return fact ? documentDisplayText(draft, fact) : id;
    }
    case "material_link": {
      const link = byId(base.material_links, id) ?? byId(draft.material_links, id);
      if (!link) return id;
      const src = byId(base.material_objects, link.source_id) ?? byId(draft.material_objects, link.source_id);
      const tgt = byId(base.material_objects, link.target_id) ?? byId(draft.material_objects, link.target_id);
      const srcText = src ? documentDisplayText(base, src) : link.source_id;
      const tgtText = tgt ? documentDisplayText(base, tgt) : link.target_id;
      return `${srcText} → ${tgtText}`;
    }
  }
}

function errorText(e: unknown): ReactNode {
  if (e instanceof ApiError) {
    const details = e.errors.map((issue) => issue.message).filter(Boolean);
    const head = e.status === 409 ? `${e.message}。你的修改仍保留，可以取消编辑后重新读取。` : e.message;
    return details.length ? (
      <div className="flex flex-col gap-1">
        <span>{head}</span>
        <ul className="m-0 pl-5">
          {details.slice(0, 8).map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ul>
      </div>
    ) : (
      head
    );
  }
  return e instanceof Error ? e.message : "保存失败";
}

export function ElementInspector() {
  const [params] = useSearchParams();
  const target = params.get("inspect");
  if (!target) return null;
  const split = target.indexOf(":");
  const kind = target.slice(0, split);
  const id = target.slice(split + 1);
  const sessionId =
    params.get("inspectSource") === "published" ? null : (params.get("inspectSession") ?? params.get("session"));
  const previewHash = params.get("inspectPreviewHash");
  return (
    <Inspector
      key={`${kind}:${id}:${sessionId}:${previewHash}`}
      kind={kind}
      id={id}
      sessionId={sessionId}
      previewHash={previewHash}
    />
  );
}

function Inspector({
  kind: requestedKind,
  id,
  sessionId,
  previewHash,
}: {
  kind: string;
  id: string;
  sessionId: string | null;
  previewHash: string | null;
}) {
  const { workspace, refresh } = useWorkspaceContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const active = usePageActive();
  const page = useContext(PageTabContext);
  const reportElement = page?.updateElement;
  const body = useRef<HTMLDivElement>(null);
  const creating = id === "new";
  const createdId = useRef(newId());
  const effectiveId = creating ? createdId.current : id;
  const owner = params.get("inspectOwner");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(
    !previewHash && (creating || params.get("inspectMode") === "edit") && !!workspace.role,
  );
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ReactNode>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [copyFallback, setCopyFallback] = useState(false);
  const [impactPreview, setImpactPreview] = useState<ImpactPreview | null>(null);
  const [notice, setNotice] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    let live = true;
    setError(null);
    const load = async () => {
      if (!KINDS.has(requestedKind)) throw new Error("不支持的元素类型");
      if (sessionId && !workspace.role) throw new Error("没有权限查看此内容");
      const current = await api.workspace(workspace.id);
      let source: Loaded;
      if (sessionId) {
        const session = await modelingApi.get(workspace.id, sessionId);
        if (previewHash) {
          const preview = await publishApi.preview(session);
          if (preview.merged_snapshot_sha256 !== previewHash)
            throw new Error("待发布内容已变化，请关闭弹窗并重新预览");
          source = { draft: preview.merged_model, session: null, versionId: preview.current_version_id };
        } else source = { draft: session.draft, session, versionId: current.version_id };
      } else {
        const model = workspace.role
          ? await modelingApi.snapshot(workspace.id)
          : current.version_id
            ? (await api.presentation(workspace.id, current.version_id)).model
            : null;
        if (!model) throw new Error("还没有发布内容");
        source = { draft: model, session: null, versionId: current.version_id };
      }
      let value = source.draft;
      if (creating) {
        if (!workspace.role) throw new Error("没有权限新建");
        if (!NEW_KINDS.includes(requestedKind as InspectKind)) throw new Error("请从所属对象或关系中新增");
        const kind = requestedKind as InspectKind;
        value = upsert(value, COLLECTION[kind], blank(value, kind, effectiveId, owner) as never);
      }
      if (live) {
        setLoaded(source);
        setDraft(value);
      }
    };
    void load().catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [workspace.id, workspace.role, requestedKind, creating, effectiveId, sessionId, previewHash, owner, attempt]);
  useLayoutEffect(() => {
    reportElement?.({ dirty, busy });
    return () => reportElement?.({ dirty: false, busy: false });
  }, [dirty, busy, reportElement]);
  useEffect(() => {
    if (!dirty && !busy) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, busy]);

  const resolved = draft ? resolve(draft, requestedKind, effectiveId) : null;
  const kind: InspectKind = resolved?.kind ?? (NEW_KINDS.includes(requestedKind as InspectKind) ? (requestedKind as InspectKind) : "object_type");
  const element = resolved?.element;
  const object = kind === "object_type" ? (element as ObjectType | undefined) : undefined;
  const link = kind === "link_type" ? (element as LinkType | undefined) : undefined;
  const properties = draft && object ? effectiveProperties(draft, object.id) : [];
  const relations = draft && object ? relationsFor(draft, object) : [];
  const rules = draft && (object || link) ? rulesFor(draft, (object ?? link)!) : [];
  const member = !!workspace.role;
  const tabs: { key: ElementTab; label: string; count?: number }[] = object
    ? [
        { key: "basic", label: "概览" },
        { key: "properties", label: "属性与映射", count: properties.length },
        { key: "relations", label: "关系", count: relations.length },
        ...(rules.length || editing ? [{ key: "rules" as const, label: "规则", count: rules.length }] : []),
        ...(member && !creating ? [{ key: "instances" as const, label: "实例" }] : []),
      ]
    : link
      ? [
          { key: "basic", label: "概览" },
          ...(member ? [{ key: "mapping" as const, label: "数据绑定" }] : []),
          ...(rules.length || editing ? [{ key: "rules" as const, label: "规则", count: rules.length }] : []),
          ...(member && !creating ? [{ key: "instances" as const, label: "实例" }] : []),
        ]
      : [];
  const requestedTab = params.get("inspectTab") ?? resolved?.tab ?? "basic";
  const compatible =
    requestedTab === "data" || (requestedTab === "mapping" && object)
      ? "properties"
      : requestedTab === "overview" || requestedTab === "endpoints"
        ? "basic"
        : requestedTab;
  const selectedTab = tabs.find((t) => t.key === compatible)?.key ?? "basic";
  const selectTab = (tab: ElementTab) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("inspectTab", tab);
        return next;
      },
      { replace: true },
    );
  useEffect(() => {
    if (!loaded || !body.current) return;
    Array.from(body.current.querySelectorAll<HTMLElement>("[data-element-id]"))
      .find((el) => el.dataset.elementId === id)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [loaded, selectedTab, id]);

  const discard = () => {
    flushSync(() => {
      setDirty(false);
      setEditing(false);
      setError(null);
      setShowErrors(false);
      setImpactPreview(null);
      setDraft(loaded?.draft ?? null);
    });
    reportElement?.({ dirty: false, busy: false });
  };
  const close = () => {
    if (busy) return;
    discard();
    void navigate(withoutInspector(createPath(location)), { replace: true });
  };
  const open = (request: ElementRequest) => {
    if (busy) return;
    if (element && request.id === element.id && request.kind === kind && request.mode !== "edit") {
      selectTab(request.tab ?? "basic");
      return;
    }
    discard();
    void navigate(
      inspectorHref(createPath(location), { ...request, sessionId, previewHash: previewHash ?? undefined }),
    );
  };
  const buildCandidate = (): { candidate: ElementSave; problem: string | null } | null => {
    if (!draft || !element || !loaded || !member || previewHash) return null;
    const value = kind === "metric" ? upsert(draft, "metrics", storedMetric(element as Metric)) : draft;
    return {
      problem: saveProblem(value, kind, element),
      candidate: {
        target_kind: kind,
        target_id: element.id,
        expected_current_version_id: loaded.versionId,
        session_id: loaded.session?.id ?? null,
        expected_session_revision: loaded.session?.revision ?? null,
        draft: value,
      },
    };
  };
  const performSave = async (payload: ElementSave) => {
    const result = await modelingApi.saveElement(workspace.id, payload);
    const next: Loaded = {
      draft: result.session?.draft ?? result.draft,
      session: result.session,
      versionId: result.version.version_id,
    };
    flushSync(() => {
      setLoaded(next);
      setDraft(next.draft);
      setImpactPreview(null);
      setDirty(false);
      setEditing(false);
      setShowErrors(false);
      setBusy(false);
    });
    reportElement?.({ dirty: false, busy: false });
    notifyOntologySaved({ workspaceId: workspace.id, session: result.session });
    refresh();
    setNotice("已保存");
    void navigate(
      inspectorHref(createPath(location), { kind, id: payload.target_id, tab: selectedTab, sessionId }),
      { replace: true },
    );
  };
  const save = async () => {
    if (busy) return;
    const built = buildCandidate();
    if (!built) return;
    if (built.problem) {
      setShowErrors(true);
      setError(built.problem);
      return;
    }
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const impact = await modelingApi.previewElementSave(workspace.id, built.candidate);
      if (impact.affected_items.length > 0) {
        setImpactPreview({
          candidate: built.candidate,
          signature: JSON.stringify(built.candidate.draft),
          items: impact.affected_items,
        });
        return;
      }
      await performSave(built.candidate);
    } catch (e) {
      setImpactPreview(null);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const confirmSave = async () => {
    if (!impactPreview || busy) return;
    const built = buildCandidate();
    if (!built) return;
    if (built.problem) {
      setImpactPreview(null);
      setShowErrors(true);
      setError(built.problem);
      return;
    }
    if (JSON.stringify(built.candidate.draft) !== impactPreview.signature) {
      setImpactPreview(null);
      await save();
      return;
    }
    const affected_items: AffectedItem[] = impactPreview.items.map(
      ({ target_kind, target_id, expected_target_hash }) => ({
        target_kind,
        target_id,
        expected_target_hash,
      }),
    );
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      setImpactPreview(null);
      await performSave({ ...built.candidate, affected_items });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const beginEdit = () => {
    if (!loaded || !draft || !member || previewHash) return;
    setEditing(true);
    setNotice("");
  };
  const cancel = () => {
    if (creating) {
      flushSync(() => {
        setDirty(false);
        setEditing(false);
      });
      reportElement?.({ dirty: false, busy: false });
      close();
    } else {
      discard();
      setAttempt((n) => n + 1);
    }
  };
  const elementLink = new URL(
    element
      ? inspectorHref(createPath(location), {
          kind,
          id: element.id,
          tab: selectedTab,
          sessionId,
          previewHash: previewHash ?? undefined,
        })
      : createPath(location),
    window.location.origin,
  ).href;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(elementLink);
      setNotice("链接已复制");
    } catch {
      setCopyFallback(true);
    }
  };
  const change = (next: Draft) => {
    setDraft(next);
    setDirty(true);
    setNotice("");
    setImpactPreview(null);
  };
  const panel: PanelProps | null =
    draft && (object || link)
      ? { draft, type: (object ?? link)!, editing, canEdit: member && !previewHash, sessionId, change, open }
      : null;
  const Icon = { object_type: Box, link_type: GitBranch, metric: Sigma, dataset: Database }[kind];
  const record = draft && object ? objectMapping(draft, object) : null;
  const title = element?.name
    ? kind === "object_type" || kind === "link_type"
      ? shortObjectName(element)
      : element.name
    : creating
      ? `新建${NOUN[kind]}`
      : NOUN[kind];
  const technical = element && "technical_name" in element ? element.technical_name : "";
  const content = (() => {
    if (!draft || !element) return null;
    if (kind === "metric")
      return (
        <MetricPanel
          draft={draft}
          metric={element as Metric}
          editing={editing}
          canPreview={member && !previewHash}
          showErrors={showErrors}
          context={
            loaded?.session
              ? { session_id: loaded.session.id, expected_session_revision: loaded.session.revision }
              : { expected_current_version_id: loaded?.versionId ?? null }
          }
          change={change}
          open={open}
        />
      );
    if (kind === "dataset")
      return <DatasetPanel draft={draft} dataset={element as Dataset} editing={editing} change={change} open={open} />;
    if (!panel) return null;
    if (object) {
      const props = panel as PanelProps<ObjectType>;
      if (selectedTab === "properties") return <PropertiesPanel {...props} />;
      if (selectedTab === "relations") return <RelationsPanel {...props} />;
      if (selectedTab === "rules") return <RulesPanel {...panel} />;
      if (selectedTab === "instances")
        return (
          <ElementInstances key={object.id} {...panel} canBrowseDatabase={!previewHash && !editing} initialObjectId={resolved?.factId} />
        );
      return <ObjectBasicPanel {...props} />;
    }
    const props = panel as PanelProps<LinkType>;
    if (selectedTab === "mapping") return <LinkMappingPanel {...props} />;
    if (selectedTab === "rules") return <RulesPanel {...panel} />;
    if (selectedTab === "instances") return <ElementInstances {...panel} canBrowseDatabase={!previewHash && !editing} />;
    return <LinkBasicPanel {...props} />;
  })();
  return (
    <Modal
      open={active}
      onCancel={close}
      maskClosable={!busy && !dirty && !impactPreview}
      keyboard={!busy && !impactPreview}
      width={expanded ? "96vw" : 1180}
      centered
      destroyOnHidden={false}
      closable={{ "aria-label": `关闭${NOUN[kind]}弹窗`, disabled: busy }}
      styles={{ body: { minHeight: 360, maxHeight: expanded ? "82vh" : "70vh", overflowY: "auto" } }}
      footer={
        editing ? (
          <div className="flex items-center justify-end gap-2">
            <Button disabled={busy} onClick={cancel}>
              取消
            </Button>
            <Button type="primary" loading={busy} disabled={!element || (!dirty && !creating)} onClick={() => void save()}>
              保存
            </Button>
          </div>
        ) : null
      }
      title={
        <div className="flex items-start gap-3 pr-8">
          <span className="mt-0.5 text-accent">
            <Icon size={28} strokeWidth={1.8} />
          </span>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="flex flex-wrap items-baseline gap-2" aria-label={element?.name || title}>
              <span className="text-lg">{title}</span>
              {technical && <code className="text-xs font-normal text-muted">{technical}</code>}
            </span>
            {draft && link && (
              <Text type="secondary" className="text-xs font-normal">
                {byId(draft.object_types, link.source_type_id)?.name} → {byId(draft.object_types, link.target_type_id)?.name}
              </Text>
            )}
            {record && record.mode !== "virtual" && record.mode !== "unbound" && (
              <span className="mt-1 flex items-center gap-2 text-xs font-normal">
                <MappingStatusIcon state={record.state} label={record.label} />
                {record.main?.dataset && <Text type="secondary">{record.main.dataset.name}</Text>}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {notice && (
              <Text type="success" className="inline-flex items-center gap-1 text-xs font-normal" role="status">
                <Check size={14} />
                {notice}
              </Text>
            )}
            {!editing && member && !previewHash && element && (
              <Button size="small" onClick={beginEdit} disabled={!loaded}>
                编辑
              </Button>
            )}
            {element && !creating && (
              <Button size="small" onClick={() => void copy()}>
                复制链接
              </Button>
            )}
            <Tooltip title={expanded ? "还原弹窗" : "展开弹窗"}>
              <Button
                size="small"
                type="text"
                aria-label={expanded ? "还原弹窗" : "展开弹窗"}
                icon={expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                onClick={() => setExpanded(!expanded)}
              />
            </Tooltip>
          </div>
        </div>
      }
    >
      <div ref={body} aria-busy={busy} className="flex flex-col gap-3">
        {tabs.length > 0 && (
          <Tabs
            size="small"
            className="sticky top-0 z-10 !mb-0 bg-surface"
            activeKey={selectedTab}
            onChange={(key) => selectTab(key as ElementTab)}
            items={tabs.map((tab) => ({
              key: tab.key,
              label: (
                <span>
                  {tab.label}
                  {tab.count !== undefined && <span className="ml-1 text-xs text-muted">{tab.count}</span>}
                </span>
              ),
            }))}
          />
        )}
        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            action={
              !draft ? (
                <Button size="small" onClick={() => setAttempt((n) => n + 1)}>
                  重新读取
                </Button>
              ) : undefined
            }
          />
        )}
        {!loaded && !error && (
          <div className="flex justify-center py-12" role="status" aria-label="正在读取">
            <Spin />
          </div>
        )}
        {loaded && !element && <Text type="secondary">此元素不存在，或已从当前内容中删除。</Text>}
        {content && <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0">{content}</fieldset>}
      </div>
      {impactPreview && draft && (
        <Modal
          open
          title="确认保存影响"
          okText="确认保存"
          cancelText="取消"
          okButtonProps={{ loading: busy }}
          cancelButtonProps={{ disabled: busy }}
          onOk={() => void confirmSave()}
          onCancel={() => !busy && setImpactPreview(null)}
          destroyOnHidden
        >
          <div className="flex flex-col gap-3">
            <Text type="secondary">确认后这些元素会随本次保存一并改写</Text>
            <List
              size="small"
              bordered
              dataSource={impactPreview.items}
              renderItem={(item) => (
                <List.Item key={`${item.target_kind}:${item.target_id}`} className="!flex-col !items-start gap-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <Tag color={KIND[item.target_kind].color} className="!m-0">
                      {KIND[item.target_kind].label}
                    </Tag>
                    <strong>{affectedElementName(draft, loaded?.draft ?? draft, item)}</strong>
                  </span>
                  <Text type="secondary" className="text-xs">
                    {item.reason}
                  </Text>
                </List.Item>
              )}
            />
          </div>
        </Modal>
      )}
      {copyFallback && (
        <InspectorDialog title="复制链接" onClose={() => setCopyFallback(false)}>
          <Input aria-label="元素链接" autoFocus readOnly value={elementLink} onFocus={(e) => e.currentTarget.select()} />
        </InspectorDialog>
      )}
    </Modal>
  );
}
