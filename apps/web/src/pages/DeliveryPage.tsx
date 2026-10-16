import { Alert, Button, Card, Empty, Table, Tabs, Tag, Typography } from "antd";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Check, CheckCircle2, Copy, Rocket } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { VersionSummary } from "../api/types";
import { LoadingSurface } from "../components/AsyncState";
import { HistoryComparison } from "../components/ReleaseReview";
import { SessionPicker } from "../components/SessionPicker";
import { PublishPanel } from "../components/publish/PublishPanel";
import { useModeling } from "../hooks/useModeling";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

const { Text, Paragraph } = Typography;

type PageTab = "publish" | "history" | "service";

const MCP_TOOLS = [
  ["search_ontology", "按名称、同义词和描述搜索对象、属性、关系、规则和指标"],
  ["get_ontology", "读取本体定义及其引用"],
  ["search_objects", "搜索文档事实实例"],
  ["get_object", "读取一个实例的属性、关联和证据"],
] as const;

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  return (
    <Button
      size="small"
      icon={state === "done" ? <Check size={14} /> : <Copy size={14} />}
      onClick={() =>
        navigator.clipboard
          .writeText(text)
          .then(() => setState("done"))
          .catch(() => setState("failed"))
      }
    >
      {state === "done" ? "已复制" : state === "failed" ? "复制失败，请手动选择" : label}
    </Button>
  );
}

export function DeliveryPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const model = useModeling(workspace.id, !!workspace.role, true);
  const [params, setParams] = useSearchParams();
  const tab: PageTab = (params.get("tab") as PageTab | null) ?? (workspace.role ? "publish" : "history");
  const setTab = (next: PageTab) =>
    setParams(
      (p) => {
        const value = new URLSearchParams(p);
        value.set("tab", next);
        return value;
      },
      { replace: true },
    );
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [result, setResult] = useState("");
  const { setError } = model;
  usePageTab({ title: model.session ? `发布 · ${model.session.title}` : undefined });
  const loadVersions = useCallback(() => api.versions(workspace.id).then((r) => setVersions(r.items)), [workspace.id]);
  useEffect(() => {
    loadVersions().catch((e: Error) => setError(e.message));
  }, [loadVersions, setError]);
  const serviceRoot = window.location.origin + "/api/v1/ontology/workspaces/" + workspace.id;
  const session = model.session;
  const picker = (
    <SessionPicker session={session} sessionId={model.sessionId} sessions={model.sessions} onSelect={model.select} />
  );
  const publish = !session ? (
    model.sessionId && !model.error ? (
      <LoadingSurface label="正在加载会话…" />
    ) : (
      <Empty image={<Rocket size={40} className="mx-auto text-muted" />} description="选择待发布的本体">
        {picker}
      </Empty>
    )
  ) : (
    <PublishPanel
      key={session.id}
      session={session}
      picker={picker}
      onSession={model.setSession}
      onStale={() => {
        // The workspace moved on: versions and header too.
        model.reload();
        void loadVersions();
        refresh();
      }}
      onPublished={(version, next) => {
        model.setSession(next);
        setResult("已发布 v" + version.version);
        void loadVersions();
        refresh();
      }}
    />
  );
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader
        title="本体发布"
        note={
          workspace.current_version && (
            <Tag color="success" className="!m-0" icon={<CheckCircle2 size={12} className="mr-1 inline" />}>
              当前 v{workspace.current_version}
            </Tag>
          )
        }
      />
      <PageBody className="!gap-3">
      <Tabs
        activeKey={tab}
        onChange={(key) => setTab(key as PageTab)}
        items={[
          ...(workspace.role
            ? [
                {
                  key: "publish",
                  label: "发布",
                  children: (
                    <div className="flex flex-col gap-3">
                      {result && <Alert type="success" showIcon message={result} />}
                      {publish}
                      {model.error && <Alert type="error" showIcon message={model.error} />}
                    </div>
                  ),
                },
              ]
            : []),
          {
            key: "history",
            label: "版本历史",
            children: (
              <div className="flex flex-col gap-3">
                {workspace.role && versions.length > 0 && (
                  <HistoryComparison workspaceId={workspace.id} versions={versions} />
                )}
                <Table
                  size="middle"
                  rowKey="version_id"
                  dataSource={versions}
                  pagination={versions.length > 20 ? { pageSize: 20 } : false}
                  locale={{ emptyText: <Empty description="还没有已发布版本" /> }}
                  columns={[
                    { title: "版本", key: "version", width: 80, render: (_, v) => `v${v.version}` },
                    { title: "说明", key: "message", render: (_, v) => v.message || <Text type="secondary">—</Text> },
                    {
                      title: "对象 / 关系 / 指标",
                      key: "counts",
                      render: (_, v) => `${v.counts.object_types} / ${v.counts.link_types} / ${v.counts.metrics}`,
                    },
                    {
                      title: "发布时间",
                      key: "published",
                      render: (_, v) => new Date(v.published_at).toLocaleString("zh-CN", { hour12: false }),
                    },
                  ]}
                />
              </div>
            ),
          },
          {
            key: "service",
            label: "服务接入",
            children: (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <Card title="REST API" size="small">
                  <code className="block break-all">{serviceRoot}/types</code>
                  <div className="mt-3 flex gap-2">
                    <CopyButton text={serviceRoot + "/types"} label="复制地址" />
                    <Button size="small" href="/docs" target="_blank">
                      查看接口文档
                    </Button>
                  </div>
                </Card>
                <Card title="MCP" size="small">
                  <code className="block break-all">{serviceRoot}/mcp</code>
                  <div className="mt-3">
                    <CopyButton text={serviceRoot + "/mcp"} label="复制地址" />
                  </div>
                  <Paragraph type="secondary" className="!mt-3 !mb-1 text-xs">
                    使用服务令牌（Bearer）调用，只读，提供四个工具：
                  </Paragraph>
                  <ul className="m-0 flex flex-col gap-1 pl-5 text-sm">
                    {MCP_TOOLS.map(([name, text]) => (
                      <li key={name}>
                        <code>{name}</code> <Text type="secondary">{text}</Text>
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>
            ),
          },
        ]}
      />
      </PageBody>
    </div>
  );
}
