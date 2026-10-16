import { Box, Check, GitBranch, Maximize2, Minimize2, X } from "lucide-react";
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
  PropertiesPanel,
  RelationsPanel,
  RulesPanel,
} from "./ElementPanels";
import {
  isObject,
  rulesFor,
  relationsFor,
  type ElementType,
  type PanelProps,
} from "../../lib/elementModel";
import { InspectorDialog } from "./InspectorDialog";
import { ActionsPanel } from "./ElementActions";
import { LinkMappingPanel } from "./LinkMappingPanel";
import { objectMapping, shortObjectName } from "../../lib/objectMapping";
import {
  mappingChangesForSave,
  mappingSaveError,
} from "../../lib/objectMappingEditing";
import { MappingStatusIcon } from "./MappingWidgets";
import { inheritedProperties } from "../../lib/elementModel";
import { ElementInstances } from "./ElementInstances";
import { newId as generateId } from "../../lib/id";

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
    return { type: draft.value_types?.find((t) => t.id === id) };
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
    if (rule) {
      if (rule.owner_kind === "link_type") {
        const relation = draft.link_types.find((r) => r.id === rule.owner_id);
        const owner =
          relation &&
          draft.object_types.find(
            (o) =>
              o.id === (relation.owner_ref?.ref || relation.source_type_id),
          );
        if (owner) return { type: owner, tab: "rules" };
      }
      return {
        ...resolve(draft, rule.owner_kind, rule.owner_id),
        tab: "rules",
      };
    }
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
  const [copyFallback, setCopyFallback] = useState(false);
  const [copied, setCopied] = useState(false);
  const [notice, setNotice] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2200);
    return () => window.clearTimeout(timer);
  }, [copied]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);
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
    draft && type
      ? [
          ...draft.properties.filter((p) => p.owner_type_id === type.id),
          ...(isObject(type)
            ? inheritedProperties(draft, type).map((p) => p.property)
            : []),
        ]
      : [];
  const relations =
    draft && type && isObject(type) ? relationsFor(draft, type) : [];
  const rules = draft && type ? rulesFor(draft, type) : [];
  const actions =
    draft && type
      ? draft.actions.filter(
          (a) =>
            a.input_type_id === type.id ||
            (!isObject(type) &&
              a.effects.some((e) => e.link_type_id === type.id)),
        )
      : [];
  const actionsTab = actions.length
    ? [{ id: "actions" as const, name: "动作", count: actions.length }]
    : [];
  const valueConcept =
    type && isObject(type) && type.concept_kind === "value_type";
  const selectedKind = valueConcept
    ? "value_type"
    : object
      ? "object_type"
      : "link_type";
  const allTabs: {
    id: ElementTab;
    name: string;
    count?: number;
    private?: boolean;
  }[] = object
    ? [
        { id: "basic", name: "概览" },
        ...(properties.length || editing
          ? [
              {
                id: "properties" as const,
                name: "属性与映射",
                count: properties.length,
              },
            ]
          : []),
        ...(relations.length
          ? [
              {
                id: "relations" as const,
                name: "关系",
                count: relations.length,
              },
            ]
          : []),
        ...(rules.length
          ? [{ id: "rules" as const, name: "规则", count: rules.length }]
          : []),
        ...actionsTab,
        { id: "instances", name: "实例", private: true },
      ]
    : [
        { id: "basic", name: "概览" },
        { id: "endpoints", name: "角色与语义描述" },
        { id: "mapping", name: "关联条件", private: true },
        ...(rules.length
          ? [{ id: "rules" as const, name: "规则", count: rules.length }]
          : []),
        ...actionsTab,
        { id: "instances", name: "实例", private: true },
      ];
  const tabs = allTabs.filter((tab) =>
    valueConcept ? tab.id === "basic" : !tab.private || workspace.role,
  );
  const requestedTab = params.get("inspectTab") ?? resolved?.tab ?? "basic";
  const compatibleTab =
    (requestedTab === "data" || requestedTab === "mapping") && object
      ? "properties"
      : requestedTab === "overview"
        ? "basic"
        : requestedTab;
  const selectedTab = tabs.find((t) => t.id === compatibleTab)?.id ?? "basic";
  const record =
    draft && type && isObject(type) && !valueConcept
      ? objectMapping(
          draft,
          type,
          loaded?.draft.schema_version === "3" ? loaded.draft : undefined,
        )
      : null;
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
    if (active && !editingIntent)
      dialog.current
        ?.querySelector<HTMLButtonElement>(`[data-tab="${selectedTab}"]`)
        ?.focus({ preventScroll: true });
  }, [loaded, selectedTab, effectiveId, active, editingIntent]);
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
    discard();
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
    discard();
    void navigate(
      inspectorHref(createPath(location), {
        ...request,
        sessionId,
        previewHash: previewHash ?? undefined,
      }),
    );
  };
  const save = async (override?: LegacyDraft): Promise<boolean> => {
    const value = override ?? draft;
    if (!value || !type || !loaded || busy || !workspace.role || previewHash)
      return false;
    if (override) {
      setDraft(override);
      setDirty(true);
    }
    const source = loaded;
    const nativeDraft =
      source.draft.schema_version === "3" ? source.draft : undefined;
    const saveError = mappingSaveError({
      draft: value,
      nativeDraft,
      type,
      editing,
      change: setDraft,
      open,
    });
    if (saveError) {
      setError(saveError);
      return false;
    }
    const savingDraft = nativeFromEditor(source.draft, value);
    if (savingDraft.schema_version === "3" && value._semantic_changes?.length) {
      const legacyBefore = editorDraft(source.draft);
      if (
        JSON.stringify(legacyBefore.mappings) ===
          JSON.stringify(value.mappings) &&
        JSON.stringify(legacyBefore.link_types.map((l) => l.data_join)) ===
          JSON.stringify(value.link_types.map((l) => l.data_join))
      )
        delete savingDraft._legacy_form;
      else {
        setError(
          "原生结构编辑与单表映射替换需要分别保存，请先取消其中一组修改。",
        );
        return false;
      }
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await modelingApi.saveElement(workspace.id, {
        target_kind: selectedKind,
        target_id: type.id,
        expected_current_version_id: loaded.versionId,
        session_id: source.session?.id ?? null,
        expected_session_revision: source.session?.revision ?? null,
        draft: savingDraft,
        semantic_changes: mappingChangesForSave(value),
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
      return true;
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? `${e.message}。你的修改仍保留，可以取消编辑后重新读取。`
          : e instanceof Error
            ? e.message
            : "保存失败",
      );
      return false;
    } finally {
      setBusy(false);
    }
  };
  const beginEdit = () => {
    if (!loaded || !draft || loading || !workspace.role || previewHash) return;
    setEditing(true);
    setNotice("");
    window.requestAnimationFrame(() =>
      body.current
        ?.querySelector<HTMLElement>("input, select, button, textarea")
        ?.focus({ preventScroll: true }),
    );
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
  const objectLink = new URL(
    type
      ? inspectorHref(createPath(location), {
          kind: selectedKind,
          id: type.id,
          tab: selectedTab,
          sessionId,
          previewHash: previewHash ?? undefined,
        })
      : createPath(location),
    window.location.origin,
  ).href;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(objectLink);
      setCopied(true);
    } catch {
      setCopyFallback(true);
    }
  };
  const props: PanelProps | null =
    draft && type
      ? {
          draft,
          nativeDraft:
            loaded?.draft.schema_version === "3" ? loaded.draft : undefined,
          type,
          editing,
          canEdit: !!workspace.role && !previewHash,
          saveError: error,
          requestEdit: beginEdit,
          saveDraft: save,
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
      onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        const bounds = e.currentTarget.getBoundingClientRect();
        if (
          e.clientX < bounds.left ||
          e.clientX > bounds.right ||
          e.clientY < bounds.top ||
          e.clientY > bounds.bottom
        )
          close();
      }}
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
            <div className="element-title">
              <h2 id={titleId} aria-label={type?.name || "本体元素"}>
                {type
                  ? shortObjectName(type)
                  : id === "new"
                    ? object
                      ? "新建对象"
                      : "新建关系"
                    : "本体元素"}
                {type?.technical_name && <code>{type.technical_name}</code>}
              </h2>
              {type && !isObject(type) && (
                <small className="element-object-status">
                  {
                    draft?.object_types.find(
                      (o) =>
                        o.id === (type.source_type_id || type.owner_ref?.ref),
                    )?.name
                  }
                  {" → "}
                  {
                    draft?.object_types.find(
                      (o) => o.id === type.target_type_id,
                    )?.name
                  }
                </small>
              )}
              {record && (
                <div className="element-object-status">
                  <MappingStatusIcon state={record.state} />
                  <span>
                    {record.label}
                    {record.mainDataset
                      ? ` · ${record.mainDataset.source}`
                      : ""}
                  </span>
                </div>
              )}
            </div>
          </div>
          <div className="element-header-actions">
            {!editing && workspace.role && !previewHash && type && (
              <button
                className="button button--secondary"
                type="button"
                onClick={beginEdit}
                disabled={loading}
              >
                编辑
              </button>
            )}
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void copy()}
            >
              {copied ? "已复制" : "复制链接"}
            </button>
            <button
              className="icon-button"
              type="button"
              aria-label={expanded ? "还原弹窗" : "展开弹窗"}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
            <button
              className="icon-button"
              type="button"
              aria-label="关闭对象弹窗"
              disabled={busy}
              onClick={close}
            >
              <X size={20} />
            </button>
          </div>
        </header>
        {object && (
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
                onClick={() => {
                  selectTab(tab.id);
                  dialog.current
                    ?.querySelector<HTMLButtonElement>(`[data-tab="${tab.id}"]`)
                    ?.focus({ preventScroll: true });
                }}
              >
                {tab.name}
                {tab.count !== undefined && <span>{tab.count}</span>}
              </button>
            ))}
          </div>
        )}
        <div
          ref={body}
          id={panelId}
          className="element-body"
          role="tabpanel"
          aria-labelledby={object ? tabId(selectedTab) : titleId}
          aria-busy={busy}
          tabIndex={0}
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
              {!object ? (
                <LinkMappingPanel {...props} />
              ) : (
                selectedTab === "basic" && <BasicPanel {...props} />
              )}
              {object && selectedTab === "properties" && (
                <PropertiesPanel
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
              {object && selectedTab === "relations" && (
                <RelationsPanel {...props} />
              )}
              {object && selectedTab === "rules" && <RulesPanel {...props} />}
              {object && selectedTab === "actions" && (
                <ActionsPanel {...props} />
              )}
              {object && selectedTab === "instances" && (
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
        <footer className="element-footer" hidden={!editing}>
          {editing && (
            <>
              <button
                className="button button--secondary om-push"
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
          )}
        </footer>
        {notice && (
          <div className="element-saved-toast" role="status">
            <Check size={14} />
            {notice}
          </div>
        )}
        {copyFallback && (
          <InspectorDialog
            title="复制链接"
            onClose={() => setCopyFallback(false)}
          >
            <label className="element-field">
              <span>对象链接</span>
              <input
                aria-label="对象链接"
                autoFocus
                readOnly
                value={objectLink}
                onFocus={(e) => e.currentTarget.select()}
              />
            </label>
          </InspectorDialog>
        )}
      </form>
    </dialog>
  );
}
