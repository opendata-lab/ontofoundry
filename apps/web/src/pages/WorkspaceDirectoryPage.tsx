import { Alert, Avatar, Button, Empty, Form, Input, Modal, Tag, Typography } from "antd";
import { ArrowRight, LockKeyhole, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { Brand } from "../components/Brand";

const { Text, Title } = Typography;

type NewWorkspace = { name: string; slug: string; description: string };

export function WorkspaceDirectoryPage() {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");
  const [form] = Form.useForm<NewWorkspace>();
  const load = useCallback(() => {
    setError("");
    Promise.all([api.workspaces(), api.me()])
      .then(([workspaceData, userData]) => {
        setWorkspaces(workspaceData.items);
        setUser(userData);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  useEffect(load, [load]);
  const createWorkspace = async (values: NewWorkspace) => {
    setCreating(true);
    setFormError("");
    try {
      const workspace = await api.createWorkspace({ ...values, description: values.description ?? "" });
      setOpen(false);
      navigate("/workspaces/" + workspace.id + "/view");
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : "工作空间创建失败");
    } finally {
      setCreating(false);
    }
  };
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!user) return <LoadingSurface label="正在读取工作空间目录…" />;
  return (
    <div className="min-h-dvh bg-canvas">
      <header className="flex h-[52px] items-center justify-between border-b border-rule-soft bg-surface px-6">
        <Brand />
        <span className="flex items-center gap-2 text-xs">
          <Avatar size={24} className="!bg-accent !text-[11px]">
            {user.display_name.slice(0, 1).toUpperCase() || "A"}
          </Avatar>
          {user.display_name}
        </span>
      </header>
      <main className="mx-auto flex max-w-[1080px] flex-col gap-5 px-6 py-8">
        <div className="flex items-end justify-between gap-4">
          <div>
            <Title level={3} className="!m-0">
              工作空间
            </Title>
            <Text type="secondary">每个工作空间维护一张独立本体图和一个当前发布版本。</Text>
          </div>
          <Button type="primary" icon={<Plus size={17} aria-hidden="true" />} onClick={() => setOpen(true)}>
            创建工作空间
          </Button>
        </div>
        {workspaces.length ? (
          <section className="flex flex-col overflow-hidden rounded-md border border-rule bg-surface" aria-label="工作空间列表">
            {workspaces.map((workspace) => (
              <Link
                key={workspace.id}
                to={"/workspaces/" + workspace.id + "/view"}
                className="grid grid-cols-[minmax(0,1fr)_96px_96px_120px_160px] items-center gap-4 border-b border-rule-soft px-5 py-4 !text-ink-2 last:border-b-0 hover:bg-surface-soft"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex size-9 flex-none items-center justify-center rounded-sm bg-accent-soft font-semibold text-accent">
                    {workspace.name.slice(0, 1)}
                  </span>
                  <span className="flex min-w-0 flex-col">
                    <strong className="truncate text-ink">{workspace.name}</strong>
                    <Text type="secondary" className="truncate text-xs">
                      {workspace.description || "尚未填写空间说明"}
                    </Text>
                  </span>
                </div>
                <div className="flex flex-col">
                  <strong className="tabular-nums">{workspace.object_type_count}</strong>
                  <Text type="secondary" className="text-xs">
                    业务对象
                  </Text>
                </div>
                <div className="flex flex-col">
                  <strong className="tabular-nums">{workspace.link_type_count}</strong>
                  <Text type="secondary" className="text-xs">
                    本体关系
                  </Text>
                </div>
                <div className="flex items-center gap-2">
                  {workspace.current_version ? (
                    <>
                      <Tag color="success" className="!m-0">
                        v{workspace.current_version}
                      </Tag>
                      <Text type="secondary" className="text-xs">
                        已发布
                      </Text>
                    </>
                  ) : (
                    <Tag className="!m-0">尚未发布</Tag>
                  )}
                </div>
                <div className="flex items-center justify-end gap-2 text-xs">
                  {workspace.visibility === "published_only" && <LockKeyhole size={14} aria-label="仅本体可见" />}
                  <span>
                    {workspace.role === "admin" ? "空间管理员" : workspace.role === "member" ? "空间成员" : "仅本体可见"}
                  </span>
                  <ArrowRight size={17} aria-hidden="true" />
                </div>
              </Link>
            ))}
          </section>
        ) : (
          <Empty description="还没有工作空间。创建后即可上传材料并开始建模。">
            <Button type="primary" onClick={() => setOpen(true)}>
              创建工作空间
            </Button>
          </Empty>
        )}
      </main>
      <Modal
        open={open}
        title="创建工作空间"
        onCancel={() => !creating && setOpen(false)}
        closable={{ "aria-label": "关闭" }}
        okText={creating ? "正在创建…" : "创建工作空间"}
        okButtonProps={{ loading: creating }}
        cancelText="取消"
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Text type="secondary">空间名称在平台内不能重复。</Text>
        <Form<NewWorkspace> form={form} layout="vertical" className="!mt-3" onFinish={(values) => void createWorkspace(values)}>
          <Form.Item name="name" label="空间名称" rules={[{ required: true, message: "请填写空间名称" }, { max: 120 }]}>
            <Input aria-label="空间名称" autoFocus />
          </Form.Item>
          <Form.Item
            name="slug"
            label="空间标识"
            extra="用于 API 地址，只能使用小写字母、数字和连字符。"
            rules={[
              { required: true, message: "请填写空间标识" },
              { pattern: /^[a-z][a-z0-9-]*$/, message: "以小写字母开头，只能使用小写字母、数字和连字符" },
            ]}
          >
            <Input aria-label="空间标识" placeholder="manufacturing-domain" />
          </Form.Item>
          <Form.Item name="description" label="空间说明" rules={[{ max: 1200 }]}>
            <Input.TextArea aria-label="空间说明" rows={3} />
          </Form.Item>
          {formError && <Alert type="error" showIcon message={formError} />}
        </Form>
      </Modal>
    </div>
  );
}
