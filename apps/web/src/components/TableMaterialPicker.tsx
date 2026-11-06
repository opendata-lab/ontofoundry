import { Alert, Button, Checkbox, Empty, Input, Modal, Select, Table, Tag, Typography, type TableProps } from "antd";
import { Database } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { datasetApi } from "../api/client";
import type { LinkedTable, RegisteredTable } from "../api/types";
import { tableKey, tableLabel } from "../lib/linkedTables";
import { syncTime } from "../lib/metadataSync";

/** Links registered tables to a modeling session; only synced tables can be used. */
export function TableMaterialPicker({
  workspaceId,
  sessionId,
  tableScope,
  linked = [],
  disabled = false,
  onSave,
  onTablesLoaded,
}: {
  workspaceId: string;
  sessionId?: string;
  tableScope?: "all" | "selected";
  linked?: LinkedTable[];
  disabled?: boolean;
  onSave: (patch: { table_scope: "all" | "selected"; linked_tables: LinkedTable[] }) => Promise<void>;
  onTablesLoaded?: (tables: RegisteredTable[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [tables, setTables] = useState<RegisteredTable[]>();
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [connection, setConnection] = useState("");
  const [schema, setSchema] = useState("");
  const [kind, setKind] = useState<"all" | "table" | "view">("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const effectiveScope = tableScope ?? (linked.length > 0 ? "selected" : "all");
  // A string key keeps a fresh `linked` array from resetting the user's choice.
  const linkedKeys = linked.map(tableKey).join("\n");
  const tablesLoaded = useRef(onTablesLoaded);
  tablesLoaded.current = onTablesLoaded;

  useEffect(() => {
    if (!open) return;
    let live = true;
    setTables(undefined);
    setError("");
    setQuery("");
    setConnection("");
    setSchema("");
    setKind("all");
    datasetApi
      .registeredTables(workspaceId, sessionId)
      .then((result) => {
        if (!live) return;
        setTables(result.items);
        tablesLoaded.current?.(result.items);
        if (effectiveScope === "all") {
          setSelectedKeys(new Set(result.items.map(tableKey)));
        } else {
          setSelectedKeys(new Set(linkedKeys ? linkedKeys.split("\n") : []));
        }
      })
      .catch((e: Error) => {
        if (!live) return;
        setTables([]);
        setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [open, workspaceId, sessionId, effectiveScope, linkedKeys]);

  const connections = useMemo(() => {
    const byId = new Map<string, string>();
    for (const t of tables ?? []) byId.set(t.connection_id, t.connection_name);
    return Array.from(byId, ([value, label]) => ({ value, label }));
  }, [tables]);

  const schemas = useMemo(() => {
    const set = new Set<string>();
    for (const t of tables ?? []) {
      if (!connection || t.connection_id === connection) {
        if (t.schema_name) set.add(t.schema_name);
      }
    }
    return Array.from(set);
  }, [tables, connection]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (tables ?? []).filter((t) => {
      if (connection && t.connection_id !== connection) return false;
      if (schema && t.schema_name !== schema) return false;
      if (kind === "table" && t.kind === "view") return false;
      if (kind === "view" && t.kind !== "view") return false;
      if (q) {
        const matchesName = t.table_name.toLowerCase().includes(q);
        const matchesSchema = (t.schema_name || "").toLowerCase().includes(q);
        const matchesComment = (t.comment || "").toLowerCase().includes(q);
        const matchesDatasets = (t.datasets || []).some(
          (d) => d.name.toLowerCase().includes(q) || (d.display_name || "").toLowerCase().includes(q),
        );
        if (!matchesName && !matchesSchema && !matchesComment && !matchesDatasets) return false;
      }
      return true;
    });
  }, [tables, connection, schema, kind, query]);

  const matchingKeys = useMemo(() => filtered.map(tableKey), [filtered]);
  const matchingSelectedCount = useMemo(
    () => matchingKeys.filter((k) => selectedKeys.has(k)).length,
    [matchingKeys, selectedKeys],
  );
  const allFilteredSelected = matchingKeys.length > 0 && matchingSelectedCount === matchingKeys.length;
  const someFilteredSelected = matchingSelectedCount > 0 && matchingSelectedCount < matchingKeys.length;

  const toggleAllFiltered = (checked: boolean) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (checked) {
        matchingKeys.forEach((k) => next.add(k));
      } else {
        matchingKeys.forEach((k) => next.delete(k));
      }
      return next;
    });
  };

  const selectAllAcrossAll = () => {
    setSelectedKeys(new Set((tables ?? []).map(tableKey)));
  };

  const clearAll = () => {
    setSelectedKeys(new Set());
  };

  const selectedCount = (tables ?? []).filter((t) => selectedKeys.has(tableKey(t))).length;
  const totalCount = tables?.length ?? 0;

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      // Count only listed tables: a saved selection may name tables no longer synced.
      const isAll = totalCount > 0 && selectedCount === totalCount;
      const patch = isAll
        ? { table_scope: "all" as const, linked_tables: [] }
        : {
            table_scope: "selected" as const,
            linked_tables: (tables ?? [])
              .filter((t) => selectedKeys.has(tableKey(t)))
              .map((t) => ({
                connection_id: t.connection_id,
                schema_name: t.schema_name,
                table_name: t.table_name,
              })),
          };
      await onSave(patch);
      setOpen(false);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "关联数据表失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleOne = (record: RegisteredTable, checked: boolean) => {
    const key = tableKey(record);
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const columns: TableProps<RegisteredTable>["columns"] = [
    {
      // Header box acts on every row matching the filters, across pages.
      title: (
        <Checkbox
          aria-label="全选"
          checked={allFilteredSelected}
          indeterminate={someFilteredSelected}
          onChange={(e) => toggleAllFiltered(e.target.checked)}
        />
      ),
      key: "select",
      width: 48,
      render: (_: unknown, record: RegisteredTable) => (
        <Checkbox
          aria-label={tableLabel(record)}
          checked={selectedKeys.has(tableKey(record))}
          onChange={(e) => toggleOne(record, e.target.checked)}
        />
      ),
    },
    {
      title: "数据表",
      key: "table_name",
      render: (_: unknown, record: RegisteredTable) => (
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-medium text-ink" title={record.table_name}>
              {record.table_name}
            </span>
            {record.kind === "view" && (
              <Tag bordered={false}>视图</Tag>
            )}
          </div>
          {record.comment ? (
            <Typography.Text type="secondary" className="truncate text-xs" title={record.comment}>
              {record.comment}
            </Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: "数据源 · 库",
      key: "source_schema",
      render: (_: unknown, record: RegisteredTable) => (
        <span className="truncate text-sm text-ink-2" title={`${record.connection_name} · ${record.schema_name || "-"}`}>
          {record.connection_name} · {record.schema_name || "-"}
        </span>
      ),
    },
    {
      title: "列数",
      dataIndex: "column_count",
      key: "column_count",
      width: 88,
      sorter: (a, b) => a.column_count - b.column_count,
      render: (count: number) => <span className="text-sm">{count}</span>,
    },
    {
      title: "已有数据集",
      dataIndex: "datasets",
      key: "datasets",
      render: (datasets: RegisteredTable["datasets"]) => {
        if (!datasets?.length) return <Typography.Text type="secondary">-</Typography.Text>;
        const names = datasets.map((d) => d.display_name || d.name).join("、");
        return (
          <span className="truncate text-xs text-ink-2" title={names}>
            {names}
          </span>
        );
      },
    },
    {
      title: "最近同步时间",
      dataIndex: "observed_at",
      key: "observed_at",
      width: 176,
      sorter: (a, b) => {
        const tA = a.observed_at ? new Date(a.observed_at).getTime() : 0;
        const tB = b.observed_at ? new Date(b.observed_at).getTime() : 0;
        return tA - tB;
      },
      render: (time: string | null) => (
        <span className="text-xs text-muted">{syncTime(time)}</span>
      ),
    },
  ];

  return (
    <>
      <Button icon={<Database size={15} />} disabled={disabled} onClick={() => setOpen(true)}>
        选择数据表…
      </Button>
      <Modal
        open={open}
        title="关联数据表"
        width="var(--data-tables-dialog-width)"
        onCancel={() => !busy && setOpen(false)}
        okText="关联到会话"
        cancelText="取消"
        okButtonProps={{ loading: busy, disabled: tables === undefined }}
        onOk={() => void save()}
      >
        <div className="flex flex-col gap-3">
          <Typography.Text type="secondary">
            只能使用已在数据管理中同步的表和视图；建模助手会在这些表上提议数据集。
          </Typography.Text>

          {tables !== undefined && !tables.length && !error ? (
            <Empty
              description={
                <span>
                  还没有已同步的数据表，请先到{" "}
                  <Link to={`/workspaces/${workspaceId}/mappings`}>数据管理</Link> 同步
                </span>
              }
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Select
                  aria-label="数据源"
                  className="w-40"
                  placeholder="全部数据源"
                  allowClear
                  value={connection || undefined}
                  onChange={(val) => {
                    setConnection(val || "");
                    setSchema("");
                  }}
                  options={[
                    { value: "", label: "全部数据源" },
                    ...connections,
                  ]}
                />
                <Select
                  aria-label="库"
                  className="w-36"
                  placeholder="全部库"
                  allowClear
                  value={schema || undefined}
                  onChange={(val) => setSchema(val || "")}
                  options={[
                    { value: "", label: "全部库" },
                    ...schemas.map((s) => ({ value: s, label: s })),
                  ]}
                />
                <Select
                  aria-label="类型"
                  className="w-28"
                  value={kind}
                  onChange={(val) => setKind(val)}
                  options={[
                    { value: "all", label: "全部类型" },
                    { value: "table", label: "数据表" },
                    { value: "view", label: "视图" },
                  ]}
                />
                <Input.Search
                  aria-label="搜索数据表"
                  className="flex-1"
                  placeholder="搜索表名、库、注释或数据集"
                  allowClear
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>

              <div className="flex items-center justify-between text-xs text-muted">
                <span>
                  匹配 {filtered.length} 张 · 已选 {selectedCount} / 共 {totalCount} 张
                </span>
                <div className="flex items-center gap-3">
                  <Button type="link" size="small" className="p-0 text-xs" onClick={selectAllAcrossAll}>
                    全选全部
                  </Button>
                  <Button type="link" size="small" className="p-0 text-xs" onClick={clearAll}>
                    清空
                  </Button>
                </div>
              </div>

              <Table<RegisteredTable>
                size="small"
                rowKey={tableKey}
                pagination={{ pageSize: 20, showSizeChanger: false }}
                scroll={{ y: "var(--table-picker-list-height)" }}
                columns={columns}
                dataSource={filtered}
                loading={tables === undefined}
                locale={{
                  emptyText: <Empty description="没有匹配的数据表" />,
                }}
              />
            </>
          )}

          {error && <Alert type="error" showIcon message={error} />}
        </div>
      </Modal>
    </>
  );
}
