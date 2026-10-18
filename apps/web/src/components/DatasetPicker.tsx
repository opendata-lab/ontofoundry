import { Alert, Button, Empty, Form, Input, Modal, Select, Table, Typography } from "antd";
import { RefreshCw, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, catalogApi } from "../api/client";
import type { AssetTable, Assets, DataConnection, Dataset, Draft, ElementSaveResult, Workspace } from "../api/types";
import { usePageActive } from "../hooks/usePageTab";
import { datasetFromTable, registerDataset, sameLocation } from "../lib/datasetEditing";
import { StatusMark } from "./layout";

const { Text } = Typography;

const CHANGES: Record<string, string> = { added: "新增", removed: "删除", changed: "变更" };



function RegisterForm({
  connection,
  table,
  draft,
  busy,
  error,
  onCancel,
  onSubmit,
}: {
  connection: DataConnection;
  table: AssetTable;
  draft: Draft;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onSubmit: (dataset: Dataset) => void;
}) {
  const [dataset, setDataset] = useState(() => datasetFromTable(connection, table, table.comment || table.name));
  const duplicates = sameLocation(draft, dataset);
  const dates = (dataset.columns ?? []).filter((c) => /date|time/i.test(c.physical_type ?? ""));
  return (
    <Modal
      open
      title={`登记数据集：${[table.schema, table.name].filter(Boolean).join(".")}`}
      onCancel={onCancel}
      okText="登记"
      cancelText="取消"
      okButtonProps={{ loading: busy, disabled: !dataset.name.trim() }}
      onOk={() => onSubmit(dataset)}
      destroyOnHidden
    >
      <Form layout="vertical" component="div" requiredMark>
        <Form.Item label="名称" required>
          <Input aria-label="数据集名称" value={dataset.name} onChange={(e) => setDataset({ ...dataset, name: e.target.value })} />
        </Form.Item>
        <Form.Item label="描述">
          <Input.TextArea
            aria-label="数据集描述"
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder="一行代表什么、数据范围和更新方式"
            value={dataset.description}
            onChange={(e) => setDataset({ ...dataset, description: e.target.value })}
          />
        </Form.Item>
        <Form.Item label="每日快照日期列" extra="表里每天保存一份全量时选择">
          <Select
            aria-label="每日快照日期列"
            allowClear
            placeholder="不是快照表"
            value={dataset.snapshot_date_column ?? undefined}
            options={dates.map((c) => ({ value: c.name, label: c.comment ? `${c.comment}（${c.name}）` : c.name }))}
            onChange={(column?: string) => setDataset({ ...dataset, snapshot_date_column: column ?? null })}
          />
        </Form.Item>
        <Text type="secondary" className="text-xs">
          将带入 {dataset.columns?.length ?? 0} 个列的名称、类型和注释。
        </Text>
        {duplicates.length > 0 && (
          <Alert
            className="mt-3"
            type="info"
            showIcon
            message={`这张表已登记为：${duplicates.map((d) => d.name).join("、")}。同一张表可以按不同用途登记多次。`}
          />
        )}
        {error && <Alert className="mt-3" type="error" showIcon message={error} />}
      </Form>
    </Modal>
  );
}

/** Browse a connection's collected structure and register tables as datasets. */
export function DatasetPicker({
  workspace,
  draft,
  sessionId,
  open,
  onClose,
  onRegistered,
  onOpenDataset,
}: {
  workspace: Workspace;
  draft: Draft | null;
  sessionId: string | null;
  open: boolean;
  onClose: () => void;
  onRegistered: (result: ElementSaveResult, dataset: Dataset) => void;
  onOpenDataset: (id: string) => void;
}) {
  const active = usePageActive();
  const [connections, setConnections] = useState<DataConnection[] | null>(null);
  const [connectionId, setConnectionId] = useState<string>();
  const [schemas, setSchemas] = useState<string[]>([]);
  const [schema, setSchema] = useState("");
  const [assets, setAssets] = useState<Assets | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState<AssetTable | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const request = useRef(0);
  useEffect(() => {
    if (!open || connections) return;
    catalogApi
      .connections(workspace.id)
      .then((r) => {
        setConnections(r.items);
        setConnectionId((current) => current ?? r.items[0]?.id);
      })
      .catch((e: Error) => setError(e.message));
  }, [open, connections, workspace.id]);
  useEffect(() => {
    if (!open || !connectionId) return;
    let live = true;
    catalogApi
      .schemas(workspace.id, connectionId)
      .then((r) => live && setSchemas(r.items))
      .catch(() => live && setSchemas([]));
    return () => {
      live = false;
    };
  }, [open, connectionId, workspace.id]);
  const load = (refresh = false) => {
    if (!connectionId) return;
    const id = ++request.current;
    setLoading(true);
    setError("");
    const params = { schema_name: schema };
    (refresh ? catalogApi.refreshAssets(workspace.id, connectionId, params) : catalogApi.assets(workspace.id, connectionId, params))
      .then((result) => id === request.current && setAssets(result))
      .catch((e: Error) => id === request.current && setError(e.message))
      .finally(() => id === request.current && setLoading(false));
  };
  useEffect(() => {
    if (open && connectionId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, connectionId, schema]);
  const connection = connections?.find((c) => c.id === connectionId);
  const normalized = query.trim().toLowerCase();
  const tables = (assets?.items ?? []).filter(
    (t) => !normalized || `${t.name} ${t.comment ?? ""}`.toLowerCase().includes(normalized),
  );
  const register = async (dataset: Dataset) => {
    if (!draft) return;
    setSaving(true);
    setSaveError("");
    try {
      const result = await registerDataset(workspace, draft, sessionId, dataset);
      setRegistering(null);
      onRegistered(result, dataset);
    } catch (e) {
      setSaveError(e instanceof ApiError || e instanceof Error ? e.message : "登记失败");
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open={open && active}
      onCancel={() => !saving && onClose()}
      title="从数据目录登记数据集"
      width={1040}
      footer={null}
      destroyOnHidden={false}
    >
      {connections && !connections.length ? (
        <Empty description="暂无数据连接">
          <Link to="../connections">
            <Button type="primary">添加数据连接</Button>
          </Link>
        </Empty>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Select
              aria-label="数据源"
              className="w-48"
              placeholder="选择数据源"
              value={connectionId}
              options={(connections ?? []).map((c) => ({ value: c.id, label: c.name }))}
              onChange={(id: string) => {
                setConnectionId(id);
                setSchema("");
                setAssets(null);
              }}
            />
            <Select
              aria-label="Schema"
              className="w-44"
              showSearch
              allowClear
              placeholder="默认 schema"
              value={schema || undefined}
              options={schemas.map((s) => ({ value: s, label: s }))}
              onChange={(value?: string) => setSchema(value ?? "")}
            />
            <Input
              type="search"
              allowClear
              prefix={<Search size={14} className="text-muted" />}
              aria-label="搜索数据表"
              placeholder="表名或注释"
              className="w-60"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <Button className="ml-auto" icon={<RefreshCw size={14} />} loading={loading} disabled={!connectionId} onClick={() => load(true)}>
              刷新表结构
            </Button>
          </div>
          {assets?.observed_at && (
            <Text type="secondary" className="text-xs">
              结构采集于 {new Date(assets.observed_at).toLocaleString("zh-CN", { hour12: false })}
              {assets.status === "stale" && " · 可能已过期"}
            </Text>
          )}
          {(error || assets?.error) && (
            <Alert type="error" showIcon message={error || assets?.error} description={assets?.observed_at ? "展示上次成功采集的结构" : undefined} />
          )}
          {!!assets?.changes.length && (
            <Alert
              type="warning"
              showIcon
              message={`本次结构变化 ${assets.changes.length} 项`}
              description={assets.changes
                .slice(0, 12)
                .map((c) => `${c.table}${c.column ? "." + c.column : ""} ${CHANGES[c.kind] ?? c.kind}`)
                .join("；")}
            />
          )}
          {assets?.status === "unobserved" ? (
            <Empty description="还没有采集表结构">
              <Button loading={loading} onClick={() => load(true)}>
                采集表结构
              </Button>
            </Empty>
          ) : (
            <Table
              size="small"
              rowKey={(t) => `${t.schema ?? ""}.${t.name}`}
              loading={loading}
              dataSource={tables}
              pagination={tables.length > 12 ? { pageSize: 12, size: "small" } : false}
              expandable={{
                expandedRowRender: (t) => (
                  <Table
                    size="small"
                    rowKey="name"
                    pagination={false}
                    dataSource={t.columns}
                    columns={[
                      { title: "列", dataIndex: "name", render: (v: string) => <code>{v}</code> },
                      { title: "类型", dataIndex: "type" },
                      {
                        title: "主键 / 可空",
                        key: "flags",
                        render: (_, c) =>
                          c.primary_key ? "主键" : c.nullable === null || c.nullable === undefined ? "—" : c.nullable ? "可空" : "非空",
                      },
                      { title: "注释", dataIndex: "comment", render: (v?: string | null) => v || "—" },
                    ]}
                  />
                ),
              }}
              columns={[
                {
                  title: "表",
                  key: "name",
                  render: (_, t) => (
                    <div className="flex flex-col">
                      <code>{[t.schema, t.name].filter(Boolean).join(".")}</code>
                      {t.comment && <Text type="secondary" className="text-xs">{t.comment}</Text>}
                    </div>
                  ),
                },
                { title: "列", key: "columns", width: 80, render: (_, t) => (t.missing ? <StatusMark state="error" label="表已缺失" /> : t.columns.length) },
                {
                  title: "已登记",
                  key: "datasets",
                  render: (_, t) =>
                    t.datasets.length ? (
                      <span className="flex flex-wrap gap-x-3">
                        {t.datasets.map((d) => (
                          <Button key={d.id} type="link" size="small" className="h-auto p-0" onClick={() => onOpenDataset(d.id)}>
                            {d.name}
                          </Button>
                        ))}
                      </span>
                    ) : (
                      <Text type="secondary">未登记</Text>
                    ),
                },
                {
                  title: "",
                  key: "action",
                  width: 110,
                  render: (_, t) =>
                    workspace.role ? (
                      <Button size="small" disabled={t.missing || !draft || !connection} onClick={() => setRegistering(t)}>
                        登记
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
        </div>
      )}
      {registering && connection && draft && (
        <RegisterForm
          connection={connection}
          table={registering}
          draft={draft}
          busy={saving}
          error={saveError}
          onCancel={() => {
            setRegistering(null);
            setSaveError("");
          }}
          onSubmit={(dataset) => void register(dataset)}
        />
      )}
    </Modal>
  );
}
