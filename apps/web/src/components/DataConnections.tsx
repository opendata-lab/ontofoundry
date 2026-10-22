import { Alert, Button, Empty, Form, Input, InputNumber, List, Modal, Popconfirm, Select, Table } from "antd";
import { Database, Pencil, PlugZap, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, catalogApi, workspaceRequest } from "../api/client";
import type { ConnectionReference, DataConnection } from "../api/types";
import { Panel, StatusMark } from "./layout";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

const PORTS: Record<DataConnection["kind"], number> = { postgresql: 5432, mysql: 3306, doris: 9030 };
const REFERENCE_LABELS: Record<ConnectionReference["type"], string> = {
  dataset: "数据集", dataset_proposal: "待审数据集提案", linked_table: "关联表",
};

type ConnectionForm = {
  name: string;
  kind: DataConnection["kind"];
  host: string;
  port: number;
  database?: string;
  username: string;
  password?: string;
};

/** Owns the connection form and exposes its opener to the page header. */
export function DataConnections({ onReady }: { onReady?: (open: () => void) => void }) {
  const { workspace } = useWorkspaceContext();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [error, setError] = useState("");
  const [references, setReferences] = useState<ConnectionReference[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  // The connection being edited; null while adding a new one.
  const [editing, setEditing] = useState<DataConnection | null>(null);
  const [form] = Form.useForm<ConnectionForm>();
  const kind = Form.useWatch("kind", form);
  useEffect(() => {
    onReady?.(() => { setEditing(null); setError(""); setReferences([]); setOpen(true); });
  }, [onReady]);
  const edit = (c: DataConnection) => {
    setEditing(c);
    setError("");
    setReferences([]);
    setOpen(true);
  };
  useEffect(() => {
    catalogApi
      .connections(workspace.id)
      .then((r) => setConnections(r.items))
      .catch((e: Error) => setError(e.message));
  }, [workspace.id]);
  const remove = async (connection: DataConnection) => {
    setDeleting(connection.id);
    setError("");
    setReferences([]);
    setStatus("");
    try {
      await workspaceRequest<void>(workspace.id, `/connections/${connection.id}`, undefined, "DELETE");
      setConnections((items) => items.filter((item) => item.id !== connection.id));
      setStatus(connection.name + "：已删除");
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除连接失败");
      if (e instanceof ApiError && e.code === "CONNECTION_IN_USE") {
        setReferences(e.references.filter((item): item is ConnectionReference => typeof item === "object" && "type" in item && "location" in item));
      }
    } finally {
      setDeleting(null);
    }
  };
  const submit = async (values: ConnectionForm) => {
    setBusy(true);
    setError("");
    try {
      values = { ...values, database: (editing?.kind ?? values.kind) === "postgresql" ? values.database : "" };
      if (editing) {
        // An empty password keeps the stored one; the engine cannot change.
        const { kind: _kind, password, ...rest } = values;
        void _kind;
        const c = await workspaceRequest<DataConnection>(workspace.id, "/connections/" + editing.id, { ...rest, ...(password ? { password } : {}) }, "PATCH");
        setConnections((cs) => cs.map((x) => (x.id === c.id ? c : x)));
        setStatus(c.name + "：已保存");
      } else {
        const c = await workspaceRequest<DataConnection>(workspace.id, "/connections", values);
        setConnections((cs) => [...cs, c]);
      }
      setOpen(false);
      setEditing(null);
      form.resetFields();
    } catch (e) {
      setError(e instanceof Error ? e.message : "连接失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="flex flex-col gap-4">
      {error && !open && <Alert type="error" showIcon message={error} description={references.length > 0 ? (
        <List size="small" split={false} dataSource={references} renderItem={(reference) => (
          <List.Item>{REFERENCE_LABELS[reference.type]} {reference.name}（{reference.location}）</List.Item>
        )} />
      ) : undefined} />}
      {status && (
        <div role="status">
          <StatusMark state="mapped" label={status} />
        </div>
      )}
      <Panel footer="使用仅需查询权限的数据库账号。实例按需查询，不全量同步源数据。">
        <Table
          size="middle"
          onHeaderRow={() => ({ className: "text-xs" })}
          rowKey="id"
          dataSource={connections}
          pagination={connections.length > 20 ? { pageSize: 20 } : false}
          locale={{
            emptyText: (
              <Empty
                image={<Database size={40} className="mx-auto text-muted" />}
                description={
                  <>
                    <strong>尚未添加数据连接</strong>
                    <br />
                    添加 MySQL、PostgreSQL 或 Doris 连接后，即可在数据映射里登记数据集。
                  </>
                }
              />
            ),
          }}
          columns={[
            {
              title: "连接名称",
              key: "name",
              render: (_, c) => (
                <span className="inline-flex items-center gap-2 font-medium">
                  <Database size={14} className="flex-none text-accent" />
                  {c.name}
                </span>
              ),
            },
            { title: "数据库类型", dataIndex: "kind" },
            {
              title: "地址",
              key: "host",
              render: (_, c) => (
                <code className="text-xs text-muted">
                  {c.host}:{c.port}{c.kind === "postgresql" ? `/${c.database}` : ""}
                </code>
              ),
            },
            {
              title: "操作",
              key: "action",
              render: (_, c) => (
                <span className="inline-flex gap-2">
                  <Button
                    size="small"
                    icon={<PlugZap size={14} />}
                    onClick={() => {
                      setStatus("");
                      setError("");
                      setReferences([]);
                      workspaceRequest(workspace.id, "/connections/" + c.id + "/test", {})
                        .then(() => setStatus(c.name + "：连接正常"))
                        .catch((e: Error) => setError(e.message));
                    }}
                  >
                    测试
                  </Button>
                  {workspace.role === "admin" && (
                    <>
                      <Button size="small" icon={<Pencil size={14} />} aria-label={`编辑 ${c.name}`} onClick={() => edit(c)}>
                        编辑
                      </Button>
                      <Popconfirm
                        title={`删除连接 ${c.name}？已同步的表结构会一起删除，不影响源数据库。`}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => remove(c)}
                        disabled={deleting !== null}
                      >
                        <Button size="small" danger icon={<Trash2 size={14} />} aria-label={`删除 ${c.name}`} loading={deleting === c.id} disabled={deleting !== null}>
                          删除
                        </Button>
                      </Popconfirm>
                    </>
                  )}
                </span>
              ),
            },
          ]}
        />
      </Panel>
      <Modal
        open={open}
        title={editing ? "编辑数据连接" : "添加数据连接"}
        onCancel={() => { if (!busy) { setOpen(false); setEditing(null); } }}
        closable={{ "aria-label": editing ? "关闭编辑连接" : "关闭添加连接" }}
        okText={busy ? "测试连接中…" : "测试并保存"}
        okButtonProps={{ loading: busy }}
        cancelText="取消"
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<ConnectionForm>
          form={form}
          layout="vertical"
          initialValues={editing
            ? { name: editing.name, kind: editing.kind, host: editing.host, port: editing.port, database: editing.database ?? "", username: editing.username }
            : { kind: "postgresql", port: PORTS.postgresql }}
          onFinish={(values) => void submit(values)}
          onValuesChange={(changed: Partial<ConnectionForm>) => {
            if (changed.kind && !editing) form.setFieldValue("port", PORTS[changed.kind]);
          }}
        >
          <Form.Item name="name" label="连接名称" rules={[{ required: true, message: "请填写连接名称" }]}>
            <Input aria-label="连接名称" />
          </Form.Item>
          <Form.Item name="kind" label="数据库类型">
            <Select
              aria-label="数据库类型"
              disabled={!!editing}
              options={[
                { value: "postgresql", label: "PostgreSQL" },
                { value: "mysql", label: "MySQL" },
                { value: "doris", label: "Apache Doris" },
              ]}
            />
          </Form.Item>
          <div className="grid grid-cols-3 gap-x-3">
            <Form.Item
              className="col-span-2"
              name="host"
              label="主机"
              rules={[{ required: true, message: "请填写主机" }]}
            >
              <Input aria-label="主机" />
            </Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true, message: "请填写端口" }]}>
              <InputNumber aria-label="端口" min={1} max={65535} className="w-full" />
            </Form.Item>
          </div>
          {/* MySQL and Doris connect to the whole server; libraries are chosen in data management.
              A PostgreSQL connection cannot be made without its database. */}
          {(editing?.kind ?? kind) === "postgresql" && (
            <Form.Item name="database" label="数据库名称" preserve={false} rules={[{ required: true, whitespace: true, message: "PostgreSQL 连接需要填写数据库名称" }]}>
              <Input aria-label="数据库名称" />
            </Form.Item>
          )}
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item name="username" label="查询用户名" rules={[{ required: true, message: "请填写用户名" }]}>
              <Input aria-label="查询用户名" autoComplete="off" />
            </Form.Item>
            <Form.Item name="password" label="密码">
              <Input.Password aria-label="密码" autoComplete="new-password" placeholder={editing ? "不修改请留空" : undefined} />
            </Form.Item>
          </div>
          {error && <Alert type="error" showIcon message={error} />}
        </Form>
      </Modal>
    </section>
  );
}
