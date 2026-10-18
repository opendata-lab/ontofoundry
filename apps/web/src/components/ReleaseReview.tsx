import { Alert, Collapse, Select, Spin, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Comparison, Json, VersionSummary } from "../api/types";

const { Text } = Typography;
const KINDS = { added: { text: "新增", color: "success" }, removed: { text: "删除", color: "error" }, changed: { text: "修改", color: "processing" } };

const json = (value: Json) =>
  value === null || value === undefined ? (
    <Text type="secondary">—</Text>
  ) : (
    <pre className="m-0 max-h-48 overflow-auto font-mono text-xs whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>
  );

function Changes({ value }: { value: Comparison }) {
  return (
    <div className="flex flex-col gap-2">
      <Text type="secondary">
        {value.changes.length} 项变化 · {value.impacts.length} 个模型内依赖
      </Text>
      {value.impacts.length > 0 && <Alert type="info" showIcon message={`影响：${value.impacts.map((i) => i.label).join("、")}`} />}
      <Table
        size="small"
        rowKey="path"
        pagination={value.changes.length > 20 ? { pageSize: 20, size: "small" } : false}
        dataSource={value.changes}
        locale={{ emptyText: "两个版本没有模型变化" }}
        columns={[
          { title: "位置", key: "path", width: 260, render: (_, c) => <code className="break-all text-xs">{c.path}</code> },
          {
            title: "变化",
            key: "kind",
            width: 72,
            render: (_, c) => <Tag color={KINDS[c.kind].color} className="!m-0">{KINDS[c.kind].text}</Tag>,
          },
          { title: "修改前", key: "before", render: (_, c) => json(c.before) },
          { title: "修改后", key: "after", render: (_, c) => json(c.after) },
        ]}
      />
    </div>
  );
}

function ComparisonBody({ workspaceId, versions }: { workspaceId: string; versions: VersionSummary[] }) {
  const [left, setLeft] = useState("");
  const [chosen, setChosen] = useState("");
  const right = chosen || versions[0]?.version_id || "";
  const [value, setValue] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setValue(null);
    setError("");
    if (right && left !== right)
      api
        .comparison(workspaceId, right, left || undefined)
        .then((r) => active && setValue(r))
        .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [workspaceId, left, right]);
  const options = versions.map((v) => ({ value: v.version_id, label: `v${v.version}` }));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-2">
          基线
          <Select
            aria-label="比较基线"
            className="w-[120px]"
            value={left}
            options={[{ value: "", label: "空基线" }, ...options]}
            onChange={setLeft}
          />
        </span>
        <span className="inline-flex items-center gap-2">
          目标
          <Select aria-label="比较目标" className="w-[120px]" value={right} options={options} onChange={setChosen} />
        </span>
      </div>
      {left === right ? (
        <Text type="secondary">请选择不同版本。</Text>
      ) : error ? (
        <Alert type="error" showIcon message={error} />
      ) : value ? (
        <Changes value={value} />
      ) : (
        <Spin />
      )}
    </div>
  );
}

export function HistoryComparison({ workspaceId, versions }: { workspaceId: string; versions: VersionSummary[] }) {
  return (
    <Collapse
      size="small"
      destroyOnHidden
      items={[{ key: "compare", label: "比较历史版本", children: <ComparisonBody workspaceId={workspaceId} versions={versions} /> }]}
    />
  );
}
