import { Alert, Button, Empty, Form, Input, InputNumber, Modal, Select, Table } from "antd";
import { Database, PlugZap } from "lucide-react";
import { useEffect, useState } from "react";
import { catalogApi, workspaceRequest } from "../api/client";
import type { DataConnection } from "../api/types";
import { Panel, PanelToolbar, SectionTitle, StatusMark } from "./layout";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

const PORTS: Record<DataConnection["kind"], number> = { postgresql: 5432, mysql: 3306, doris: 9030 };

type ConnectionForm = {
  name: string;
  kind: DataConnection["kind"];
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
};

/** Owns the connection form and exposes its opener to the page header. */
export function DataConnections({ onReady }: { onReady?: (open: () => void) => void }) {
  const { workspace } = useWorkspaceContext();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ConnectionForm>();
  useEffect(() => {
    onReady?.(() => setOpen(true));
  }, [onReady]);
  useEffect(() => {
    catalogApi
      .connections(workspace.id)
      .then((r) => setConnections(r.items))
      .catch((e: Error) => setError(e.message));
  }, [workspace.id]);
  const submit = async (values: ConnectionForm) => {
    setBusy(true);
    setError("");
    try {
      const c = await workspaceRequest<DataConnection>(workspace.id, "/connections", values);
      setConnections((cs) => [...cs, c]);
      setOpen(false);
      form.resetFields();
    } catch (e) {
      setError(e instanceof Error ? e.message : "连接失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="flex flex-col gap-4">
      {error && !open && <Alert type="error" showIcon message={error} />}
      {status && (
        <div role="status">
          <StatusMark state="mapped" label={status} />
        </div>
      )}
      <Panel footer="使用仅需查询权限的数据库账号。实例按需查询，不全量同步源数据。">
        <PanelToolbar>
          <SectionTitle title="连接列表" note={`${connections.length} 个连接`} />
        </PanelToolbar>
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
            { title: "数据库", key: "database", render: (_, c) => <code className="text-xs">{c.database}</code> },
            {
              title: "地址",
              key: "host",
              render: (_, c) => (
                <code className="text-xs text-muted">
                  {c.host}:{c.port}
                </code>
              ),
            },
            {
              title: "操作",
              key: "action",
              render: (_, c) => (
                <Button
                  size="small"
                  icon={<PlugZap size={14} />}
                  onClick={() => {
                    setStatus("");
                    workspaceRequest(workspace.id, "/connections/" + c.id + "/test", {})
                      .then(() => setStatus(c.name + "：连接正常"))
                      .catch((e: Error) => setError(e.message));
                  }}
                >
                  测试
                </Button>
              ),
            },
          ]}
        />
      </Panel>
      <Modal
        open={open}
        title="添加数据连接"
        onCancel={() => !busy && setOpen(false)}
        closable={{ "aria-label": "关闭添加连接" }}
        okText={busy ? "测试连接中…" : "测试并保存"}
        okButtonProps={{ loading: busy }}
        cancelText="取消"
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form<ConnectionForm>
          form={form}
          layout="vertical"
          initialValues={{ kind: "postgresql", port: PORTS.postgresql }}
          onFinish={(values) => void submit(values)}
          onValuesChange={(changed: Partial<ConnectionForm>) => {
            if (changed.kind) form.setFieldValue("port", PORTS[changed.kind]);
          }}
        >
          <Form.Item name="name" label="连接名称" rules={[{ required: true, message: "请填写连接名称" }]}>
            <Input aria-label="连接名称" />
          </Form.Item>
          <Form.Item name="kind" label="数据库类型">
            <Select
              aria-label="数据库类型"
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
          <Form.Item name="database" label="数据库名称" rules={[{ required: true, message: "请填写数据库名称" }]}>
            <Input aria-label="数据库名称" />
          </Form.Item>
          <div className="grid grid-cols-2 gap-x-3">
            <Form.Item name="username" label="查询用户名" rules={[{ required: true, message: "请填写用户名" }]}>
              <Input aria-label="查询用户名" autoComplete="off" />
            </Form.Item>
            <Form.Item name="password" label="密码">
              <Input.Password aria-label="密码" autoComplete="new-password" />
            </Form.Item>
          </div>
          {error && <Alert type="error" showIcon message={error} />}
        </Form>
      </Modal>
    </section>
  );
}
