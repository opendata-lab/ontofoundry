import { Button, Empty, Input, Table, Tabs, Tag, Typography } from "antd";
import { Database, Search } from "lucide-react";
import { useMemo, useState } from "react";
import type { Dataset } from "../api/types";
import { DocumentMaterials } from "../components/DocumentMaterials";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { DatasetPicker } from "../components/DatasetPicker";
import { PageBody, PageHeader, Panel, PanelToolbar } from "../components/layout";
import { useElementDetail } from "../hooks/useElementDetail";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { metricsOnDataset } from "../lib/coreModel";
import { notifyOntologySaved } from "../lib/elementInspector";
import { objectMappings } from "../lib/objectMapping";

const { Text } = Typography;

export function MappingsPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const detail = useElementDetail();
  const snapshot = useSnapshot(workspace);
  const draft = snapshot.draft;
  useErrorMessage(snapshot.error);
  const [tab, setTab] = useState<"datasets" | "documents">("datasets");
  const [query, setQuery] = useState("");
  const [picker, setPicker] = useState(false);
  const records = useMemo(() => (draft ? objectMappings(draft) : []), [draft]);
  const normalized = query.trim().toLowerCase();
  const datasets = (draft?.datasets ?? []).filter(
    (d) => !normalized || [d.name, d.table_name, d.schema_name ?? "", d.description].join(" ").toLowerCase().includes(normalized),
  );
  const openDataset = (id: string) => detail.open({ kind: "dataset", id, sessionId: snapshot.sessionId });
  const usage = (dataset: Dataset) =>
    draft ? records.filter((r) => r.sources.some((s) => s.dataset_id === dataset.id)).length : 0;
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="数据管理" note={snapshot.sessionId ? "建模会话草稿" : undefined} />
      <PageBody>
        <Panel>
          <PanelToolbar
            extra={tab === "datasets" &&
              <>
                <Input
                  type="search"
                  allowClear
                  size="small"
                  prefix={<Search size={14} className="text-muted" />}
                  aria-label="搜索数据集"
                  placeholder="名称或表名"
                  className="w-60"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {workspace.role && (
                  <Button size="small" icon={<Database size={14} />} onClick={() => setPicker(true)}>
                    从数据目录登记
                  </Button>
                )}
              </>
            }
          >
            <Tabs
              activeKey={tab}
              onChange={(key) => setTab(key as typeof tab)}
              items={[
                { key: "datasets", label: `数据集 ${draft?.datasets.length ?? ""}` },
                { key: "documents", label: "文档" },
              ]}
            />
          </PanelToolbar>
          {tab === "datasets" ? (
            <Table
              size="middle"
              rowKey="id"
              loading={!draft && !snapshot.error}
              dataSource={datasets}
              pagination={datasets.length > 20 ? { pageSize: 20 } : false}
              onRow={(d) => ({ onDoubleClick: () => openDataset(d.id) })}
              locale={{
                emptyText: <Empty description={query ? "没有匹配的数据集" : "还没有登记数据集"} />,
              }}
              columns={[
                {
                  title: "数据集",
                  key: "name",
                  render: (_, d) => (
                    <div className="flex flex-col gap-1">
                      <Button type="link" size="small" className="h-auto self-start p-0 font-medium" onClick={() => openDataset(d.id)}>
                        {d.name}
                      </Button>
                      {d.description && (
                        <Text type="secondary" className="max-w-md truncate text-xs">
                          {d.description}
                        </Text>
                      )}
                    </div>
                  ),
                },
                {
                  title: "物理位置",
                  key: "location",
                  render: (_, d) => <code className="text-xs">{[d.schema_name, d.table_name].filter(Boolean).join(".")}</code>,
                },
                { title: "字段", key: "columns", width: 72, render: (_, d) => d.columns?.length ?? <Text type="secondary">未登记</Text> },
                {
                  title: "快照",
                  key: "snapshot",
                  width: 140,
                  render: (_, d) => (d.snapshot_date_column ? <Tag className="m-0">每日 · {d.snapshot_date_column}</Tag> : "—"),
                },
                { title: "对象", key: "objects", width: 72, render: (_, d) => usage(d) },
                { title: "指标", key: "metrics", width: 72, render: (_, d) => (draft ? metricsOnDataset(draft, d.id).length : "—") },
              ]}
            />
          ) : (
            <DocumentMaterials workspace={workspace} />
          )}
        </Panel>
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
