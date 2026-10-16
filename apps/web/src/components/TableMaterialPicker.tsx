import { Alert, Button, Checkbox, Empty, Input, Modal, Select, Spin, Typography } from "antd";
import { Database, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { catalogApi } from "../api/client";
import type { DataConnection, DataTable, Material } from "../api/types";
import { HintIcon } from "./HintIcon";

const { Text } = Typography;

const HINT =
  "读取所选表的字段、主键、样例值和关联字段，生成一份结构说明加入材料；开始建模后由智能体提出业务对象、数据映射和关系。";

/**
 * Bottom-up modeling input. The chosen tables are described server-side
 * (columns, keys, samples, join hints) as a Markdown material, which the run
 * reads like any document and answers with objects, mappings and joins.
 * Tables are picked in a dialog: a real database has far more tables than the
 * side panel can list.
 */
export function TableMaterialPicker({
  workspaceId,
  disabled,
  onMaterial,
}: {
  workspaceId: string;
  disabled: boolean;
  onMaterial: (material: Material) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [connections, setConnections] = useState<DataConnection[] | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [tables, setTables] = useState<DataTable[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    catalogApi
      .connections(workspaceId)
      .then((r) => {
        setConnections(r.items);
        if (r.items.length === 1) setConnectionId(r.items[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, [workspaceId]);
  useEffect(() => {
    setTables(null);
    setChosen([]);
    if (!connectionId) return;
    let active = true;
    catalogApi
      .tables(workspaceId, connectionId)
      .then((r) => active && setTables(r.items))
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [workspaceId, connectionId]);
  if (connections && !connections.length)
    return (
      <div className="flex flex-col items-start gap-2 rounded-md border border-dashed border-rule-strong p-3">
        <strong className="text-[13px]">还没有数据连接</strong>
        <Link to="../connections">
          <Button size="small" icon={<Database size={14} />}>
            新增数据连接
          </Button>
        </Link>
      </div>
    );
  const needle = query.trim().toLowerCase();
  const visible = (tables ?? []).filter((t) => !needle || `${t.schema ?? ""}.${t.name}`.toLowerCase().includes(needle));
  const toggle = (name: string) => setChosen((c) => (c.includes(name) ? c.filter((n) => n !== name) : [...c, name]));
  const close = () => {
    setOpen(false);
    setQuery("");
  };
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const material = await catalogApi.tableMaterial(workspaceId, connectionId, chosen);
      await onMaterial(material);
      setChosen([]);
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取数据表失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex items-center gap-2">
      <Button icon={<Database size={15} />} disabled={disabled || !connections} onClick={() => setOpen(true)}>
        选择数据表…
      </Button>
      <HintIcon text={HINT} />
      <Modal
        open={open}
        title="选择业务数据表"
        width={640}
        onCancel={() => !busy && close()}
        closable={{ "aria-label": "关闭选择数据表" }}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={close} disabled={busy}>
              取消
            </Button>
            <Button type="primary" disabled={!chosen.length} loading={busy} onClick={() => void generate()}>
              {busy ? "正在读取表结构…" : `加入建模材料${chosen.length ? `（${chosen.length} 张表）` : ""}`}
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Select
              aria-label="数据连接"
              className="min-w-[200px]"
              placeholder="选择数据连接"
              value={connectionId || undefined}
              disabled={busy}
              options={(connections ?? []).map((c) => ({ value: c.id, label: c.name }))}
              onChange={setConnectionId}
            />
            <Input.Search
              allowClear
              aria-label="搜索数据表"
              placeholder="搜索表名"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {connectionId && (
            <div className="flex items-center gap-2">
              <Text type="secondary" className="text-xs">
                已选 {chosen.length} / 共 {tables?.length ?? 0} 张表
              </Text>
              <Button
                size="small"
                type="link"
                disabled={!visible.length || busy}
                onClick={() => setChosen((c) => [...new Set([...c, ...visible.map((t) => t.name)])])}
              >
                全选筛选结果
              </Button>
              <Button size="small" type="link" disabled={!chosen.length || busy} onClick={() => setChosen([])}>
                清空
              </Button>
            </div>
          )}
          <div className="flex max-h-[360px] flex-col gap-1 overflow-auto" role="group" aria-label="选择数据表">
            {!connectionId && <Text type="secondary">先选择数据连接</Text>}
            {connectionId && !tables && <Spin />}
            {tables && !visible.length && <Empty description="没有匹配的数据表" />}
            {visible.map((t) => {
              const keys = t.columns.filter((c) => c.primary_key).map((c) => c.name);
              return (
                <Checkbox
                  key={`${t.schema ?? ""}.${t.name}`}
                  aria-label={t.name}
                  checked={chosen.includes(t.name)}
                  disabled={busy}
                  onChange={() => toggle(t.name)}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Table2 size={14} aria-hidden="true" />
                    <span>{t.name}</span>
                    {/* The list endpoint may omit columns; never show a misleading "0 列". */}
                    {(t.schema || t.columns.length > 0) && (
                      <Text type="secondary" className="text-xs">
                        {[t.schema, t.columns.length ? `${t.columns.length} 列` : "", keys.length ? `主键 ${keys.join(", ")}` : ""]
                          .filter(Boolean)
                          .join(" · ")}
                      </Text>
                    )}
                  </span>
                </Checkbox>
              );
            })}
          </div>
          {error && <Alert type="error" showIcon message={error} />}
        </div>
      </Modal>
    </div>
  );
}
