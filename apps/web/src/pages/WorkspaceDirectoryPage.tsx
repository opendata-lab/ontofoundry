import { Alert, Avatar, Button, Empty, Form, Input, Modal, Table, Typography } from "antd";
import { ArrowRight, LockKeyhole, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { Brand } from "../components/Brand";
import {
  DirectoryFrame,
  PageBody,
  PageHeader,
  Panel,
  PageToolbar,
  StatusMark,
} from "../components/layout";

const { Text } = Typography;

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
    <DirectoryFrame
      header={
        <>
          <Brand />
          <span className="flex items-center gap-2 text-xs">
            <Avatar size="small" className="bg-accent text-xs">
              {user.display_name.slice(0, 1).toUpperCase() || "A"}
            </Avatar>
            {user.display_name}
          </span>
        </>
      }
    >
      <PageHeader title="工作空间" note="每个工作空间维护一张独立本体图和一个当前发布版本。" />
      <PageBody>
        <PageToolbar extra={<Text type="secondary" className="text-xs">{workspaces.length} 个工作空间</Text>}>
        <Button type="primary" icon={<Plus size={14} aria-hidden="true" />} onClick={() => setOpen(true)}>
          创建工作空间
        </Button>
        </PageToolbar>
        <Panel>
          <Table
            size="middle"
            onHeaderRow={() => ({ className: "text-xs" })}
            rowKey="id"
            dataSource={workspaces}
            pagination={workspaces.length > 20 ? { pageSize: 20 } : false}
            locale={{
              emptyText: (
                <Empty description="还没有工作空间。创建后即可上传材料并开始建模。">
                  <Button type="primary" onClick={() => setOpen(true)}>
                    创建工作空间
                  </Button>
                </Empty>
              ),
            }}
            columns={[
              {
                title: "工作空间",
                key: "name",
                render: (_, workspace) => (
                  <Link to={"/workspaces/" + workspace.id + "/view"} className="flex min-w-0 items-center gap-3">
                    <Avatar aria-hidden="true" shape="square" className="bg-accent-soft text-sm font-semibold text-accent">
                      {workspace.name.slice(0, 1)}
                    </Avatar>
                    <span className="flex min-w-0 flex-col gap-1">
                      <strong className="text-ink">{workspace.name}</strong>
                      <Text type="secondary" className="text-xs">
                        {workspace.description || "尚未填写空间说明"}
                      </Text>
                    </span>
                  </Link>
                ),
              },
              { title: "业务对象", dataIndex: "object_type_count", className: "tabular-nums" },
              { title: "本体关系", dataIndex: "link_type_count", className: "tabular-nums" },
              {
                title: "发布版本",
                key: "version",
                render: (_, workspace) => (
                  <StatusMark
                    state={workspace.current_version ? "mapped" : "unmapped"}
                    label={workspace.current_version ? `v${workspace.current_version} · 已发布` : "尚未发布"}
                  />
                ),
              },
              {
                title: "访问权限",
                key: "access",
                render: (_, workspace) => (
                  <span className="inline-flex items-center gap-2 text-xs text-muted">
                    {workspace.visibility === "published_only" && <LockKeyhole size={14} aria-label="仅本体可见" />}
                    {workspace.role === "admin"
                      ? "空间管理员"
                      : workspace.role === "member"
                        ? "空间成员"
                        : "仅本体可见"}
                  </span>
                ),
              },
              {
                title: "",
                key: "open",
                render: (_, workspace) => (
                  <Link to={"/workspaces/" + workspace.id + "/view"} aria-label={`进入 ${workspace.name}`}>
                    <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                ),
              },
            ]}
          />
        </Panel>
      </PageBody>
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
        <Form<NewWorkspace>
          form={form}
          layout="vertical"
          className="mt-3"
          onFinish={(values) => void createWorkspace(values)}
        >
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
    </DirectoryFrame>
  );
}
