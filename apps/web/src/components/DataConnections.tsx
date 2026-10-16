import { Alert, Button, Card, Empty, Form, Input, InputNumber, Modal, Select, Typography } from "antd";
import { Database, PlugZap } from "lucide-react";
import { useEffect, useState } from "react";
import { catalogApi, workspaceRequest } from "../api/client";
import type { DataConnection } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

const { Text } = Typography;
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

/**
 * 数据连接管理。
 *
 * 只负责内容，不含标题——标题归页面。新建弹窗由组件持有（表单状态在这里），
 * 触发按钮通过 onReady 交给页面工具栏，和其他页的主操作位置保持一致。
 */
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
      <Text type="secondary">使用仅需查询权限的数据库账号。实例按需查询，不全量同步源数据。</Text>
      {error && !open && <Alert type="error" showIcon message={error} />}
      {status && <Alert type="success" showIcon role="status" message={status} />}
      {connections.length ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
          {connections.map((c) => (
            <Card key={c.id} size="small">
              <div className="flex items-start gap-3">
                <Database size={23} className="flex-none text-accent" />
                <div className="flex min-w-0 flex-1 flex-col">
                  <Text strong className="truncate">
                    {c.name}
                  </Text>
                  <Text className="text-xs">
                    {c.kind} · {c.database}
                  </Text>
                  <Text type="secondary" className="text-xs">
                    {c.host}:{c.port}
                  </Text>
                </div>
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
              </div>
            </Card>
          ))}
        </div>
      ) : (
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
      )}
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
          <div className="grid grid-cols-[1fr_140px] gap-x-3">
            <Form.Item name="host" label="主机" rules={[{ required: true, message: "请填写主机" }]}>
              <Input aria-label="主机" />
            </Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true, message: "请填写端口" }]}>
              <InputNumber aria-label="端口" min={1} max={65535} className="!w-full" />
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
