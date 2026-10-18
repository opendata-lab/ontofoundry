import { Alert, Button, Empty, Input, Progress, Segmented, Table, Tabs, Tag, Typography } from "antd";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Database } from "lucide-react";
import { useMemo, useState } from "react";
import type { Dataset } from "../api/types";
import { DatasetPicker } from "../components/DatasetPicker";
import { MappingStatusIcon } from "../components/elements/MappingWidgets";
import { datasetLabel } from "../lib/datasetEditing";
import { useElementInspector } from "../hooks/useElementInspector";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { identifier, metricsOnDataset } from "../lib/coreModel";
import { notifyOntologySaved } from "../lib/elementInspector";
import { BINDING_MODES, objectMappings, shortObjectName, type ObjectMapping } from "../lib/objectMapping";

const { Text } = Typography;

type Filter = "all" | ObjectMapping["state"];

export function MappingsPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const inspector = useElementInspector();
  const snapshot = useSnapshot(workspace);
  const draft = snapshot.draft;
  const [tab, setTab] = useState<"datasets" | "mappings">("datasets");
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [picker, setPicker] = useState(false);
  const records = useMemo(() => (draft ? objectMappings(draft) : []), [draft]);
  const normalized = query.trim().toLowerCase();
  const rows = records.filter(
    (r) =>
      (filter === "all" || (r.mode !== "virtual" && r.state === filter)) &&
      (!normalized ||
        [r.object.name, r.object.technical_name, ...r.sources.map((s) => s.dataset?.name ?? "")]
          .join(" ")
          .toLowerCase()
          .includes(normalized)),
  );
  const datasets = (draft?.datasets ?? []).filter(
    (d) => !normalized || [d.name, d.table_name, d.schema_name ?? "", d.description].join(" ").toLowerCase().includes(normalized),
  );
  const openDataset = (id: string) => inspector.open({ kind: "dataset", id, sessionId: snapshot.sessionId });
  const openObject = (record: ObjectMapping) =>
    inspector.open({ kind: "object_type", id: record.object.id, tab: "properties", sessionId: snapshot.sessionId });
  const usage = (dataset: Dataset) =>
    draft ? records.filter((r) => r.sources.some((s) => s.dataset_id === dataset.id)).length : 0;
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="数据映射" note={snapshot.sessionId ? "建模会话草稿" : "当前版本"}>
        {workspace.role && (
          <Button icon={<Database size={14} />} onClick={() => setPicker(true)}>
            从数据目录登记
          </Button>
        )}
      </PageHeader>
      <PageBody className="!gap-3">
      {snapshot.error && <Alert type="error" showIcon message={snapshot.error} />}
      <Tabs
        activeKey={tab}
        onChange={(key) => setTab(key as typeof tab)}
        items={[
          { key: "datasets", label: `数据集 ${draft?.datasets.length ?? ""}` },
          { key: "mappings", label: `本体映射 ${records.length || ""}` },
        ]}
        tabBarExtraContent={
          <Input.Search
            allowClear
            size="small"
            aria-label={tab === "datasets" ? "搜索数据集" : "搜索对象或数据集"}
            placeholder={tab === "datasets" ? "名称或表名" : "对象、英文名或数据集"}
            className="w-[260px]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        }
      />
      {tab === "datasets" ? (
        <Table
          size="middle"
          rowKey="id"
          loading={!draft && !snapshot.error}
          dataSource={datasets}
          pagination={datasets.length > 20 ? { pageSize: 20 } : false}
          onRow={(d) => ({ onDoubleClick: () => openDataset(d.id) })}
          locale={{
            emptyText: (
              <Empty description={query ? "没有匹配的数据集" : "还没有登记数据集"}>
                {workspace.role && !query && <Button onClick={() => setPicker(true)}>从数据目录登记</Button>}
              </Empty>
            ),
          }}
          columns={[
            {
              title: "数据集",
              key: "name",
              render: (_, d) => (
                <div className="flex flex-col">
                  <Button type="link" className="!h-auto self-start !p-0" onClick={() => openDataset(d.id)}>
                    {d.name}
                  </Button>
                  {d.description && (
                    <Text type="secondary" className="max-w-[420px] truncate text-xs">
                      {d.description}
                    </Text>
                  )}
                </div>
              ),
            },
            {
              title: "物理位置",
              key: "location",
              render: (_, d) => <code>{[d.schema_name, d.table_name].filter(Boolean).join(".")}</code>,
            },
            { title: "列", key: "columns", width: 72, render: (_, d) => d.columns?.length ?? <Text type="secondary">未登记</Text> },
            {
              title: "快照",
              key: "snapshot",
              width: 140,
              render: (_, d) => (d.snapshot_date_column ? <Tag className="!m-0">每日 · {d.snapshot_date_column}</Tag> : "—"),
            },
            { title: "对象", key: "objects", width: 72, render: (_, d) => usage(d) || "—" },
            { title: "指标", key: "metrics", width: 72, render: (_, d) => (draft ? metricsOnDataset(draft, d.id).length || "—" : "—") },
          ]}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <Segmented
            className="self-start"
            value={filter}
            onChange={(value) => setFilter(value as Filter)}
            options={(
              [
                ["all", "全部"],
                ["mapped", "已映射"],
                ["partial", "部分映射"],
                ["unmapped", "未映射"],
              ] as const
            ).map(([value, label]) => ({
              value,
              label: `${label} ${value === "all" ? records.length : records.filter((r) => r.mode !== "virtual" && r.state === value).length}`,
            }))}
          />
          <Table
            size="middle"
            rowKey={(r) => r.object.id}
            loading={!draft && !snapshot.error}
            dataSource={rows}
            pagination={rows.length > 20 ? { pageSize: 20 } : false}
            onRow={(r) => ({ onClick: () => openObject(r), className: "cursor-pointer" })}
            locale={{
              emptyText: (
                <Empty description="没有匹配的对象">
                  {(query || filter !== "all") && (
                    <Button
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                      }}
                    >
                      清除筛选
                    </Button>
                  )}
                </Empty>
              ),
            }}
            columns={[
              {
                title: "业务对象",
                key: "object",
                render: (_, r) => (
                  <div className="flex flex-col">
                    <span>{shortObjectName(r.object)}</span>
                    <code className="text-xs text-muted">{r.object.technical_name}</code>
                  </div>
                ),
              },
              {
                title: "标识",
                key: "identifier",
                render: (_, r) => {
                  const keys = draft ? identifier(draft, r.object.id) : [];
                  return keys.length ? keys.map((p) => p.name).join(" + ") : <Text type="secondary">—</Text>;
                },
              },
              { title: "实例来源", key: "mode", width: 140, render: (_, r) => BINDING_MODES[r.mode] },
              {
                title: "主数据集",
                key: "main",
                render: (_, r) =>
                  r.main ? (
                    <span className="flex flex-col">
                      {datasetLabel(r.main.dataset)}
                      {r.sources.length > 1 && <Text type="secondary" className="text-xs">另有 {r.sources.length - 1} 个来源</Text>}
                    </span>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
              {
                title: "属性覆盖",
                key: "coverage",
                width: 220,
                render: (_, r) =>
                  r.mode === "virtual" ? (
                    <Text type="secondary">实例来自子对象</Text>
                  ) : (
                    <div className="flex flex-col gap-1">
                      <Progress percent={r.total ? Math.round((100 * r.covered) / r.total) : 0} size="small" format={() => `${r.covered}/${r.total}`} />
                      <span className="self-start">
                        <MappingStatusIcon state={r.state} label={r.label} />
                      </span>
                    </div>
                  ),
              },
            ]}
          />
          <Text type="secondary" className="text-xs">
            属性覆盖只统计已绑定的属性；继承属性按父对象或本对象的绑定计算。关系的绑定在关系弹窗中查看。
          </Text>
        </div>
      )}
      <DatasetPicker
        workspace={workspace}
        draft={draft}
        sessionId={snapshot.sessionId}
        open={picker}
        onClose={() => setPicker(false)}
        onOpenDataset={(id) => {
          setPicker(false);
          openDataset(id);
        }}
        onRegistered={(result) => {
          notifyOntologySaved({ workspaceId: workspace.id, session: result.session });
          refresh();
          snapshot.load();
        }}
      />
      </PageBody>
    </div>
  );
}
