import { Box, Database, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { modelingApi } from "../api/client";
import type { DataConnection } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useSnapshot } from "../hooks/useSnapshot";
import { usePageTab } from "../hooks/usePageTab";
import { useElementInspector } from "../hooks/useElementInspector";
import { nativeSemanticModels } from "../lib/semanticEditing";
import { editorDraft } from "../lib/nativeDraft";
import { emptyDraft, fromView } from "../lib/draftView";
import {
  objectMapping,
  shortObjectName,
  type ObjectMapping,
} from "../lib/objectMapping";
import { SemanticModels } from "../components/SemanticModels";
import { DataAssets } from "../components/DataAssets";
import { DatasetPicker } from "../components/DatasetPicker";
import { InspectorDialog } from "../components/elements/InspectorDialog";
import {
  InfoButton,
  MappingStatusIcon,
} from "../components/elements/MappingWidgets";

const FILTERS = [
  ["all", "全部"],
  ["mapped", "已映射"],
  ["partial", "部分映射"],
  ["unmapped", "未映射"],
] as const;
export function MappingsPage() {
  const { workspace } = useWorkspaceContext();
  const inspector = useElementInspector();
  const snapshot = useSnapshot(workspace);
  const [filter, setFilter] = useState<"all" | ObjectMapping["state"]>("all");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"assets" | "mappings" | "semantic">(
    "assets",
  );
  const [picker, setPicker] = useState(false);
  const [assetBusy, setAssetBusy] = useState(false);
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [info, setInfo] = useState<{ title: string; tables?: string[] } | null>(
    null,
  );
  usePageTab({ busy: assetBusy });
  useEffect(() => {
    let live = true;
    modelingApi
      .connections(workspace.id)
      .then((result) => {
        if (live) setConnections(result.items);
      })
      .catch(() => {
        if (live) setConnections([]);
      });
    return () => {
      live = false;
    };
  }, [workspace.id]);
  const source = snapshot.sourceDraft;
  const nativeDraft = source?.schema_version === "3" ? source : undefined;
  const draft = useMemo(
    () =>
      source
        ? editorDraft(source)
        : snapshot.draft
          ? editorDraft(fromView(emptyDraft(workspace.id), snapshot.draft))
          : null,
    [source, snapshot.draft, workspace.id],
  );
  const records = useMemo(
    () =>
      draft?.object_types.map((object) =>
        objectMapping(draft, object, nativeDraft),
      ) ?? [],
    [draft, nativeDraft],
  );
  const rows = records.filter(
    (record) =>
      (filter === "all" || record.state === filter) &&
      [
        record.object.name,
        record.object.technical_name,
        ...record.tables.map((t) => t.source),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const open = (record: ObjectMapping) =>
    inspector.open({
      kind: "object_type",
      id: record.object.id,
      tab: "properties",
      sessionId: snapshot.sessionId,
    });
  return (
    <div
      className={`ref-catalog om-mappings-page${view === "semantic" ? " ref-catalog--semantic" : ""}`}
    >
      <header className="catalog-toolbar">
        <h1>数据映射</h1>
        <div className="toolbar-spacer" />
        <button
          type="button"
          className="button button--secondary"
          disabled={assetBusy}
          onClick={() => setPicker(true)}
        >
          <Database size={14} />
          浏览数据目录
        </button>
      </header>
      <div className="management-tabs" role="group" aria-label="数据映射视图">
        <button
          type="button"
          aria-pressed={view === "assets"}
          disabled={assetBusy}
          onClick={() => setView("assets")}
        >
          数据源与资产
        </button>
        <button
          type="button"
          aria-pressed={view === "mappings"}
          disabled={assetBusy}
          onClick={() => setView("mappings")}
        >
          本体映射
        </button>
        <button
          type="button"
          aria-pressed={view === "semantic"}
          disabled={assetBusy}
          onClick={() => setView("semantic")}
        >
          语义模型
        </button>
      </div>
      {snapshot.error && (
        <p className="inline-error" role="alert">
          {snapshot.error}
        </p>
      )}
      {view === "assets" ? (
        <div className="management-content">
          <DataAssets
            key={workspace.id + ":" + snapshot.sessionId}
            onBusyChange={setAssetBusy}
            workspaceId={workspace.id}
            connections={connections}
            draft={snapshot.draft}
            sessionId={snapshot.sessionId}
          />
        </div>
      ) : view === "semantic" ? (
        <div className="management-content">
          <SemanticModels
            workspaceId={workspace.id}
            sessionId={snapshot.sessionId}
            canEdit={!!workspace.role}
            onBusyChange={setAssetBusy}
          />
        </div>
      ) : (
      <div className="om-panel">
        <div className="om-tabbar" role="group" aria-label="映射状态">
          {FILTERS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
            >
              {label}
              <small>
                {value === "all"
                  ? records.length
                  : records.filter((r) => r.state === value).length}
              </small>
            </button>
          ))}
        </div>
        <div className="om-toolbar">
          <label className="om-search">
            <Search size={16} />
            <input
              aria-label="搜索对象、英文名或表"
              placeholder="搜索对象、英文名或表"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <span className="om-push muted">{rows.length} 个对象</span>
        </div>
        <table className="om-table om-page-table">
          <thead>
            <tr>
              <th>业务对象</th>
              <th>标识字段</th>
              <th>来源表</th>
              <th>
                覆盖{" "}
                <InfoButton
                  label="覆盖怎么算"
                  onClick={() => setInfo({ title: "覆盖怎么算" })}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((record) => {
              const extra = record.tables.filter(
                (d) => d.id !== record.mainDataset?.id,
              );
              return (
                <tr
                  key={record.object.id}
                  className="om-open-row"
                  onClick={() => open(record)}
                >
                  <td data-label="业务对象">
                    <button
                      type="button"
                      className="om-table-object"
                      onClick={(e) => {
                        e.stopPropagation();
                        open(record);
                      }}
                    >
                      <Box size={16} />
                      {shortObjectName(record.object)}
                    </button>
                    <small className="om-sub">
                      {record.object.technical_name} · 对象
                    </small>
                  </td>
                  <td data-label="标识字段">
                    {record.keys.length ? (
                      <>
                        <code>
                          {record.keys.map((e) => e.expression).join(" + ")}
                        </code>
                        <span className="om-tag-key" title="实例标识">
                          标识
                        </span>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td data-label="来源表">
                    {record.mainDataset ? (
                      <>
                        <code>{record.mainDataset.source}</code>
                        {extra.length > 0 && (
                          <span onClick={(e) => e.stopPropagation()}>
                            <InfoButton
                              label="相关表"
                              onClick={() =>
                                setInfo({
                                  title: "相关表",
                                  tables: extra.map((t) => t.source),
                                })
                              }
                            />
                          </span>
                        )}
                        <small className="om-sub">
                          {draft?.mappings.find(
                            (m) => m.type_id === record.object.id,
                          )?.connection_alias ??
                            record.models.find((m) =>
                              m.datasets.some(
                                (d) => d.id === record.mainDataset?.id,
                              ),
                            )?.name}
                        </small>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td data-label="覆盖">
                    <div className="om-coverage">
                      <span>
                        {record.covered}/{record.total}
                      </span>
                      {record.total > 0 && (
                        <span className="om-coverage-track">
                          <i
                            style={{
                              width: `${(100 * record.covered) / record.total}%`,
                            }}
                          />
                        </span>
                      )}
                    </div>
                    <span className={`om-status om-status-${record.state}`}>
                      <MappingStatusIcon state={record.state} />
                      {record.label}
                    </span>
                  </td>
                </tr>
              );
            })}
            {!draft && !snapshot.error ? (
              <tr>
                <td colSpan={4} className="om-blank" role="status">
                  正在读取对象映射…
                </td>
              </tr>
            ) : (
              !rows.length && (
                <tr>
                  <td colSpan={4} className="om-blank">
                    没有匹配对象{" "}
                    <button
                      type="button"
                      className="element-text-button"
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                      }}
                    >
                      清除筛选
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
        <div className="om-panel-foot">
          <span className="om-push">
            {snapshot.sessionId ? "建模会话草稿" : "当前版本"}
          </span>
        </div>
      </div>
      )}
      <DatasetPicker
        workspaceId={workspace.id}
        onOpenObject={(id) =>
          inspector.open({
            kind: "object_type",
            id,
            tab: "properties",
            sessionId: snapshot.sessionId,
          })
        }
        open={picker}
        onClose={() => {
          if (!assetBusy) setPicker(false);
        }}
        datasets={
          nativeDraft
            ? nativeSemanticModels(nativeDraft).flatMap((m) => m.datasets)
            : []
        }
        draft={draft ?? undefined}
        nativeDraft={nativeDraft}
      />
      {info && (
        <InspectorDialog title={info.title} onClose={() => setInfo(null)}>
          {info.tables ? (
            info.tables.map((table) => (
              <div className="om-entry" key={table}>
                <code>{table}</code>
              </div>
            ))
          ) : (
            <p>
              覆盖只统计已绑定的属性。同一属性来自多张表也只统计一次。关系配置情况只在关系页显示；继承的属性只在合并表中展示一次。
            </p>
          )}
        </InspectorDialog>
      )}
    </div>
  );
}
