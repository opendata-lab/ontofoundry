import {
  Box,
  Check,
  GitBranch,
  Link as LinkIcon,
  Maximize2,
  Minimize2,
  X,
} from "lucide-react";
import {
  useContext,
  useEffect,
  useLayoutEffect,
  useId,
  useRef,
  useState,
} from "react";
import { flushSync } from "react-dom";
import {
  createPath,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  api,
  ApiError,
  modelingApi,
  publishApi,
  workspaceRequest,
} from "../../api/client";
import { editorDraft, nativeFromEditor } from "../../lib/nativeDraft";
import type {
  Draft,
  LegacyDraft,
  ModelingSession,
  TargetKind,
  VersionSummary,
} from "../../api/types";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { PageTabContext, usePageActive } from "../../hooks/usePageTab";
import {
  inspectorHref,
  notifyOntologySaved,
  withoutInspector,
  type ElementRequest,
  type ElementTab,
} from "../../lib/elementInspector";
import {
  BasicPanel,
  EndpointsPanel,
  EvidenceSection,
  MappingPanel,
  PropertiesPanel,
  RelationsPanel,
  RulesPanel,
} from "./ElementPanels";
import {
  isObject,
  rulesFor,
  type ElementType,
  type PanelProps,
} from "../../lib/elementModel";
import { ActionsPanel } from "./ElementActions";
import { ElementInstances } from "./ElementInstances";
import { newId as generateId } from "../../lib/id";
import "../../styles/element-inspector.css";

type Loaded = {
  draft: Draft;
  session: ModelingSession | null;
  versionId: string | null;
};
const KINDS: TargetKind[] = [
  "object_type",
  "value_type",
  "property",
  "link_type",
  "rule",
  "action",
  "material_object",
  "material_link",
  "mapping",
];
function resolve(
  draft: LegacyDraft,
  kind: string,
  id: string,
): { type: ElementType | undefined; tab?: ElementTab; objectId?: string } {
  if (kind === "value_type")
    return { type: draft.value_types?.find(t => t.id === id) };
  if (kind === "object_type")
    return { type: draft.object_types.find((t) => t.id === id) };
  if (kind === "link_type")
    return { type: draft.link_types.find((t) => t.id === id) };
  if (kind === "property")
    return {
      type: draft.object_types.find(
        (t) =>
          t.id === draft.properties.find((p) => p.id === id)?.owner_type_id,
      ),
      tab: "properties",
    };
  if (kind === "action")
    return {
      type: draft.object_types.find(
        (t) => t.id === draft.actions.find((a) => a.id === id)?.input_type_id,
      ),
      tab: "actions",
    };
  if (kind === "mapping")
    return {
      type: draft.object_types.find(
        (t) => t.id === draft.mappings.find((m) => m.id === id)?.type_id,
      ),
      tab: "mapping",
    };
  if (kind === "material_object") {
    const object = draft.material_objects.find((o) => o.id === id);
    return {
      type: draft.object_types.find((t) => t.id === object?.type_id),
      tab: "instances",
      objectId: object?.id,
    };
  }
  if (kind === "material_link")
    return {
      type: draft.link_types.find(
        (t) => t.id === draft.material_links.find((l) => l.id === id)?.type_id,
      ),
      tab: "instances",
    };
  if (kind === "rule") {
    const rule = draft.rules.find((r) => r.id === id);
    if (rule)
      return {
        ...resolve(draft, rule.owner_kind, rule.owner_id),
        tab: "rules",
      };
  }
  return { type: undefined };
}

export function ElementInspector() {
  const [params, setParams] = useSearchParams();
  const target = params.get("inspect");
  if (!target) return null;
  const split = target.indexOf(":");
  const kind = target.slice(0, split);
  const id = target.slice(split + 1);
  const sourceSession =
    params.get("inspectSource") === "published"
      ? null
      : (params.get("inspectSession") ?? params.get("session"));
  const previewHash = params.get("inspectPreviewHash");
  return (
    <Inspector
      key={`${kind}:${id}:${sourceSession}:${previewHash}`}
      kind={kind}
      id={id}
      sessionId={sourceSession}
      previewHash={previewHash}
      setParams={setParams}
    />
  );
}

function Inspector({
  kind,
  id,
  sessionId,
  previewHash,
  setParams,
}: {
  kind: string;
  id: string;
  sessionId: string | null;
  previewHash: string | null;
  setParams: ReturnType<typeof useSearchParams>[1];
}) {
  const { workspace, refresh } = useWorkspaceContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const active = usePageActive();
  const page = useContext(PageTabContext);
  const reportElement = page?.updateElement;
  const identity = useId();
  const titleId = `${identity}-title`;
  const panelId = `${identity}-panel`;
  const tabId = (tab: string) => `${identity}-tab-${tab}`;
  const dialog = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<LegacyDraft | null>(null);
  const [editingIntent, setEditing] = useState(
    !previewHash && params.get("inspectMode") === "edit" && !!workspace.role,
  );
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const newId = useRef(generateId());
  const effectiveId = id === "new" ? newId.current : id;
  useEffect(() => {
    let live = true;
    setError("");
    setLoading(true);
    const load = async () => {
      if (!KINDS.includes(kind as TargetKind))
        throw new Error("不支持的本体元素");
      if (sessionId && !workspace.role) throw new Error("没有权限查看此内容");
      const current = await api.workspace(workspace.id);
      let source: Loaded;
      if (sessionId) {
        const session = await modelingApi.get(workspace.id, sessionId);
        if (previewHash) {
          const preview = await publishApi.preview(session);
          if (
            !preview.merged_model ||
            preview.merged_snapshot_sha256 !== previewHash
          )
            throw new Error("待发布内容已变化，请关闭弹窗并重新预览");
          source = {
            draft: preview.merged_model,
            session: null,
            versionId: preview.current_version_id,
          };
        } else
          source = {
            draft: session.draft,
            session,
            versionId: current.version_id,
          };
      } else {
        const model = current.version_id
          ? (
              await workspaceRequest<{ model: Draft; version: VersionSummary }>(
                workspace.id,
                `/versions/${current.version_id}/presentation`,
              )
            ).model
          : await modelingApi.snapshot(workspace.id);
        source = { draft: model, session: null, versionId: current.version_id };
      }
      let value = editorDraft(source.draft);
      if (id === "new") {
        if (!workspace.role) throw new Error("没有权限创建本体元素");
        const base = {
          id: effectiveId,
          name: "",
          technical_name: "",
          description: "",
          tags: [],
          evidence: [],
        };
        if (kind === "object_type")
          value = {
            ...value,
            object_types: [...value.object_types, { ...base, extends: [] }],
          };
        else if (kind === "link_type")
          value = {
            ...value,
            link_types: [
              ...value.link_types,
              {
                ...base,
                source_type_id: value.object_types[0]?.id ?? "",
                target_type_id:
                  value.object_types[1]?.id ?? value.object_types[0]?.id ?? "",
                multiplicity: "many_to_many",
                verbalizes: [],
              },
            ],
          };
        else throw new Error("请从所属对象或关系中新增元素");
      }
      if (live) {
        setLoaded(source);
        setDraft(value);
      }
    };
    void load()
      .catch((e: Error) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [
    workspace.id,
    workspace.role,
    kind,
    id,
    effectiveId,
    sessionId,
    previewHash,
    attempt,
  ]);
  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (active && !el.open) el.showModal();
    if (!active && el.open) el.close();
    return () => {
      if (el.open) el.close();
    };
  }, [active]);
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
  const resolved = draft ? resolve(draft, kind, effectiveId) : null;
  const type = resolved?.type;
  const object = type ? isObject(type) : kind !== "link_type";
  const editing = editingIntent;
  const properties =
    draft?.properties.filter((p) => p.owner_type_id === type?.id) ?? [];
  const mappings = draft?.mappings.filter((m) => m.type_id === type?.id) ?? [];
  const relations =
    draft?.link_types.filter(
      (r) => r.source_type_id === type?.id || r.target_type_id === type?.id || r.owner_ref?.ref === type?.id || r.roles?.some(role => role.concept.ref === type?.id),
    ) ?? [];
  const rules = draft && type ? rulesFor(draft, type) : [];
  const actions =
    draft && type
      ? draft.actions.filter((a) =>
          object
            ? a.input_type_id === type.id
            : a.effects.some((e) => e.link_type_id === type.id),
        )
      : [];
  const valueConcept = type && isObject(type) && type.concept_kind === "value_type";
  const selectedKind = valueConcept ? "value_type" : object ? "object_type" : "link_type";
  const allTabs: {
    id: ElementTab;
    name: string;
    count?: number;
    private?: boolean;
  }[] = [
    { id: "basic", name: "基本信息" },
    object
      ? { id: "properties", name: "属性", count: properties.length }
      : { id: "endpoints", name: "角色与语义描述" },
    {
      id: "mapping",
      name: "映射",
      count: object ? mappings.length : undefined,
      private: true,
    },
    ...(object
      ? [{ id: "relations" as const, name: "关系", count: relations.length }]
      : []),
    { id: "rules", name: "规则", count: rules.length },
    { id: "actions", name: "动作", count: actions.length },
    { id: "instances", name: "实例", private: true },
  ];
  const tabs = allTabs.filter((tab) => valueConcept ? tab.id === "basic" : !tab.private || workspace.role);
  const requestedTab = params.get("inspectTab") ?? resolved?.tab ?? "basic";
  const compatibleTab = requestedTab === "data" ? "mapping" : requestedTab;
  const selectedTab = tabs.find((t) => t.id === compatibleTab)?.id ?? "basic";
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
      .find((el) => el.dataset.elementId === effectiveId)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [loaded, selectedTab, effectiveId]);
  const discard = () => {
    flushSync(() => {
      setDirty(false);
      setEditing(false);
      setError("");
      setDraft(loaded ? editorDraft(loaded.draft) : null);
    });
    reportElement?.({ dirty: false, busy: false });
  };
  const close = () => {
    if (busy) return;
    void navigate(withoutInspector(createPath(location)), { replace: true });
  };
  const open = (request: ElementRequest) => {
    if (busy) return;
    if (
      type &&
      request.id === type.id &&
      request.kind === selectedKind &&
      request.mode !== "edit"
    ) {
      selectTab(request.tab ?? "basic");
      return;
    }
    void navigate(
      inspectorHref(createPath(location), {
        ...request,
        sessionId,
        previewHash: previewHash ?? undefined,
      }),
    );
  };
  const save = async () => {
    if (!draft || !type || !loaded || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const source = loaded;
      const result = await modelingApi.saveElement(workspace.id, {
        target_kind: selectedKind,
        target_id: type.id,
        expected_current_version_id: loaded.versionId,
        session_id: source.session?.id ?? null,
        expected_session_revision: source.session?.revision ?? null,
        draft: nativeFromEditor(source.draft, draft),
        semantic_changes: draft._semantic_changes ?? [],
      });
      const next: Loaded = {
        draft: result.session?.draft ?? result.draft,
        session: result.session,
        versionId: result.version.version_id,
      };
      flushSync(() => {
        setLoaded(next);
        setDraft(editorDraft(next.draft));
        setDirty(false);
        setEditing(false);
        setBusy(false);
      });
      reportElement?.({ dirty: false, busy: false });
      notifyOntologySaved({
        workspaceId: workspace.id,
        session: result.session,
      });
      refresh();
      setNotice("已保存");
      const target = inspectorHref(createPath(location), {
        kind: selectedKind,
        id: type.id,
        tab: selectedTab,
        sessionId,
      });
      void navigate(target, { replace: true });
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? `${e.message}。你的修改仍保留，可以取消编辑后重新读取。`
          : e instanceof Error
            ? e.message
            : "保存失败",
      );
    } finally {
      setBusy(false);
    }
  };
  const beginEdit = () => {
    if (!loaded || !draft || loading) return;
    setEditing(true);
    setNotice("");
  };
  const cancel = () => {
    if (id === "new") {
      flushSync(() => {
        setDirty(false);
        setEditing(false);
      });
      reportElement?.({ dirty: false, busy: false });
      close();
    } else {
      discard();
      setLoading(true);
      setAttempt((n) => n + 1);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(
        new URL(createPath(location), window.location.origin).href,
      );
      setNotice("链接已复制");
    } catch {
      setError("复制失败，请从浏览器地址栏复制链接。");
    }
  };
  const props: PanelProps | null =
    draft && type
      ? {
          draft,
          nativeDraft: loaded?.draft.schema_version === "3" ? loaded.draft : undefined,
          type,
          editing,
          change: (next) => {
            setDraft(next);
            setDirty(true);
            setNotice("");
          },
          open,
        }
      : null;
  return (
    <dialog
      ref={dialog}
      className={`element-inspector${expanded ? " element-inspector--expanded" : ""}`}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <header className="element-header">
          <div
            className={`element-identity ${object ? "" : "element-identity--relation"}`}
          >
            {object ? (
              <Box size={38} strokeWidth={1.8} />
            ) : (
              <GitBranch size={38} strokeWidth={1.8} />
            )}
            <h2 id={titleId}>
              {type?.name ||
                (id === "new"
                  ? object
                    ? "新建对象"
                    : "新建关系"
                  : "本体元素")}
            </h2>
          </div>
          <div className="element-header-actions">
            {notice && (
              <span className="element-saved" role="status">
                <Check size={14} />
                {notice}
              </span>
            )}
            {editing ? (
              <>
                <button
                  className="button button--secondary"
                  type="button"
                  disabled={busy}
                  onClick={cancel}
                >
                  取消
                </button>
                <button
                  className="button button--primary"
                  type="submit"
                  disabled={busy || !type || (!dirty && id !== "new")}
                >
                  {busy ? "保存中…" : "保存"}
                </button>
              </>
            ) : (
              <>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => void copy()}
                >
                  <LinkIcon size={14} />
                  复制链接
                </button>
                {workspace.role && !previewHash && type && (
                  <button
                    className="button button--primary"
                    type="button"
                    onClick={beginEdit}
                    disabled={!type || loading}
                  >
                    编辑
                  </button>
                )}
              </>
            )}
            <button
              className="icon-button"
              type="button"
              aria-label={expanded ? "恢复窗口" : "最大化"}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
            <button
              className="icon-button"
              type="button"
              aria-label="关闭本体元素"
              disabled={busy}
              onClick={close}
            >
              <X size={20} />
            </button>
          </div>
        </header>
        <div
          className="element-tabs"
          role="tablist"
          aria-label="本体元素内容"
          onKeyDown={(e) => {
            const index = tabs.findIndex((t) => t.id === selectedTab);
            const next =
              e.key === "ArrowRight"
                ? (index + 1) % tabs.length
                : e.key === "ArrowLeft"
                  ? (index - 1 + tabs.length) % tabs.length
                  : e.key === "Home"
                    ? 0
                    : e.key === "End"
                      ? tabs.length - 1
                      : -1;
            if (next < 0) return;
            e.preventDefault();
            selectTab(tabs[next].id);
            dialog.current
              ?.querySelector<HTMLButtonElement>(
                `[data-tab="${tabs[next].id}"]`,
              )
              ?.focus();
          }}
        >
          {tabs.map((tab) => (
            <button
              id={tabId(tab.id)}
              role="tab"
              data-tab={tab.id}
              type="button"
              key={tab.id}
              aria-selected={selectedTab === tab.id}
              aria-controls={panelId}
              tabIndex={selectedTab === tab.id ? 0 : -1}
              onClick={() => selectTab(tab.id)}
            >
              {tab.name}
              {tab.count !== undefined && <span>{tab.count}</span>}
            </button>
          ))}
        </div>
        <div
          ref={body}
          id={panelId}
          className="element-body"
          role="tabpanel"
          aria-labelledby={tabId(selectedTab)}
          aria-busy={busy}
        >
          {error && (
            <div className="element-error" role="alert">
              <p>{error}</p>
              {!draft && (
                <button
                  type="button"
                  className="element-text-button"
                  onClick={() => setAttempt((n) => n + 1)}
                >
                  重新读取
                </button>
              )}
            </div>
          )}
          {!loaded && !error && (
            <p className="element-empty" role="status">
              正在读取本体元素…
            </p>
          )}
          {loaded && !type && (
            <p className="element-empty">
              此元素不存在，或已从当前内容中删除。
            </p>
          )}
          {props && (
            <fieldset disabled={busy || loading}>
              {selectedTab === "basic" && (
                <>
                  <BasicPanel {...props} />
                  <EvidenceSection
                    workspaceId={workspace.id}
                    evidence={type!.evidence}
                  />
                </>
              )}
              {selectedTab === "properties" && <PropertiesPanel {...props} />}
              {selectedTab === "endpoints" && <EndpointsPanel {...props} />}
              {selectedTab === "mapping" && (
                <MappingPanel
                  {...props}
                  suggestedSource={
                    params.get("mapping_source") && params.get("mapping_table")
                      ? {
                          connection_alias: params.get("mapping_source")!,
                          table_name: params.get("mapping_table")!,
                          schema_name: params.get("mapping_schema") || null,
                        }
                      : undefined
                  }
                />
              )}
              {selectedTab === "relations" && <RelationsPanel {...props} />}
              {selectedTab === "rules" && <RulesPanel {...props} />}
              {selectedTab === "actions" && <ActionsPanel {...props} />}
              {selectedTab === "instances" && (
                <ElementInstances
                  key={type!.id}
                  {...props}
                  sessionId={sessionId}
                  canBrowseDatabase={!previewHash && !editing}
                  initialObjectId={resolved?.objectId}
                />
              )}
            </fieldset>
          )}
        </div>
      </form>
    </dialog>
  );
}
