import {
  Alert,
  App,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Table,
  Tag,
  Typography,
} from "antd";
import { ArrowLeft, Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, adminApi, api } from "../api/client";
import type {
  AdminUser,
  AdminUserWorkspace,
  AdminWorkspace,
  User,
  WorkspaceRole,
} from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { NoAccessResult } from "../components/NoAccessResult";
import { PlatformFrame } from "../components/PlatformFrame";
import { PageHeader } from "../components/PageHeader";
import { PageBody, PageToolbar, Panel } from "../components/layout";
import { ROLE_OPTIONS } from "../hooks/useWorkspacePermissions";

const { Text } = Typography;

type CreateUserValues = {
  username: string;
  display_name: string;
  email?: string;
};

function formatLoginTime(iso: string | null) {
  if (!iso) return null;
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function adminErrorText(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.code === "LAST_ADMIN") return error.message || "该空间至少需要一名管理员";
    if (error.code === "USERNAME_EXISTS") return error.message || "用户名已存在";
    if (error.code === "PLATFORM_ADMIN_REQUIRED") return error.message || "需要平台管理员权限";
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

/** Platform admin user management and workspace assignment (/admin/users). */
export function AdminUsersPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();

  const [me, setMe] = useState<User | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [pageError, setPageError] = useState("");

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [workspaces, setWorkspaces] = useState<AdminWorkspace[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [query, setQuery] = useState("");
  const userRequestSeq = useRef(0);

  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createForm] = Form.useForm<CreateUserValues>();

  const [drawerUserId, setDrawerUserId] = useState<string | null>(null);
  const [addWsId, setAddWsId] = useState<string | undefined>(undefined);
  const [addRole, setAddRole] = useState<WorkspaceRole>("member");
  const [drawerBusy, setDrawerBusy] = useState(false);
  const [drawerError, setDrawerError] = useState("");

  const loadAdminData = useCallback(async (q: string) => {
    const seq = ++userRequestSeq.current;
    setLoadingList(true);
    try {
      const [userRes, wsRes] = await Promise.all([
        adminApi.users(q.trim() || undefined),
        adminApi.workspaces(),
      ]);
      if (seq !== userRequestSeq.current) return;
      setUsers(userRes.items);
      setWorkspaces(wsRes.items);
    } catch (e) {
      if (seq !== userRequestSeq.current) return;
      if (e instanceof ApiError && e.status === 403) {
        setForbidden(true);
        return;
      }
      setPageError(e instanceof Error ? e.message : "加载用户列表失败");
    } finally {
      if (seq === userRequestSeq.current) setLoadingList(false);
    }
  }, []);

  const loadMe = useCallback(() => {
    setPageError("");
    setForbidden(false);
    api
      .me()
      .then((u) => {
        setMe(u);
        if (!u.is_platform_admin) setForbidden(true);
      })
      .catch((e: Error) => setPageError(e.message));
  }, []);

  useEffect(loadMe, [loadMe]);

  useEffect(() => {
    if (!me?.is_platform_admin || forbidden) return;
    void loadAdminData(query);
  }, [me?.is_platform_admin, forbidden, query, loadAdminData]);

  const workspaceMap = useMemo(
    () => new Map(workspaces.map((w) => [w.id, w])),
    [workspaces],
  );
  const drawerUser = useMemo(
    () => users.find((u) => u.id === drawerUserId) ?? null,
    [users, drawerUserId],
  );
  const assignedWsIds = useMemo(
    () => new Set((drawerUser?.workspaces ?? []).map((w) => w.id)),
    [drawerUser],
  );
  const availableWorkspaces = useMemo(
    () => workspaces.filter((w) => !assignedWsIds.has(w.id)),
    [workspaces, assignedWsIds],
  );

  if (pageError) return <ErrorSurface message={pageError} retry={loadMe} />;
  if (!me) return <LoadingSurface label="正在检查访问权限…" />;

  if (forbidden || !me.is_platform_admin) {
    return (
      <PlatformFrame user={me}>
        <NoAccessResult subtitle="只有平台管理员（ADMIN_USERS）可以访问用户管理。" />
      </PlatformFrame>
    );
  }

  const refreshUsers = async () => {
    const seq = ++userRequestSeq.current;
    const res = await adminApi.users(query.trim() || undefined);
    if (seq === userRequestSeq.current) setUsers(res.items);
  };

  const handleCreateUser = async (values: CreateUserValues) => {
    const username = values.username.trim();
    const display_name = values.display_name.trim();
    const email = values.email?.trim() || undefined;
    setCreateError("");
    setCreateBusy(true);
    try {
      await adminApi.createUser({ username, display_name, ...(email ? { email } : {}) });
      setCreateOpen(false);
      createForm.resetFields();
      await refreshUsers();
      void message.success(`已创建用户 ${username}`);
    } catch (e) {
      setCreateError(adminErrorText(e, "创建用户失败"));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleAddWorkspace = async () => {
    if (!drawerUser || !addWsId) return;
    setDrawerError("");
    setDrawerBusy(true);
    try {
      await adminApi.setUserWorkspace(drawerUser.id, addWsId, addRole);
      setAddWsId(undefined);
      setAddRole("member");
      await refreshUsers();
      void message.success("已分配工作空间");
    } catch (e) {
      const msg = adminErrorText(e, "分配工作空间失败");
      setDrawerError(msg);
      void message.error(msg);
    } finally {
      setDrawerBusy(false);
    }
  };

  const handleRoleChange = async (workspaceId: string, role: WorkspaceRole) => {
    if (!drawerUser) return;
    setDrawerError("");
    setDrawerBusy(true);
    try {
      await adminApi.setUserWorkspace(drawerUser.id, workspaceId, role);
      await refreshUsers();
      void message.success("空间角色已更新");
    } catch (e) {
      const msg = adminErrorText(e, "更新空间角色失败");
      setDrawerError(msg);
      void message.error(msg);
    } finally {
      setDrawerBusy(false);
    }
  };

  const handleRemoveWs = async (workspaceId: string) => {
    if (!drawerUser) return;
    setDrawerError("");
    setDrawerBusy(true);
    try {
      await adminApi.removeUserWorkspace(drawerUser.id, workspaceId);
      await refreshUsers();
      void message.success("已从工作空间移除");
    } catch (e) {
      const msg = adminErrorText(e, "移除工作空间失败");
      setDrawerError(msg);
      void message.error(msg);
    } finally {
      setDrawerBusy(false);
    }
  };

  return (
    <PlatformFrame user={me}>
      <PageHeader
        title="用户管理"
        note="按用户名识别用户，支持预建账号并提前分配空间；平台管理员角色由配置文件 ADMIN_USERS 推导。"
      >
        <Button icon={<ArrowLeft size={14} />} onClick={() => navigate("/")}>
          返回工作空间
        </Button>
      </PageHeader>
      <PageBody>
        <PageToolbar
          extra={
            <>
              <Text type="secondary" className="text-xs">
                {users.length} 位用户
              </Text>
              <Input
                type="search"
                allowClear
                aria-label="搜索用户名或显示名"
                prefix={<Search size={14} className="text-muted" />}
                placeholder="搜索用户名或显示名"
                className="w-60"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </>
          }
        >
          <Button
            type="primary"
            icon={<Plus size={14} />}
            onClick={() => {
              setCreateError("");
              setCreateOpen(true);
            }}
          >
            新建用户
          </Button>
        </PageToolbar>
        <Panel>
          <Table<AdminUser>
            size="middle"
            rowKey="id"
            loading={loadingList}
            dataSource={users}
            onHeaderRow={() => ({ className: "text-xs" })}
            pagination={users.length > 20 ? { pageSize: 20 } : false}
            locale={{
              emptyText: <Empty description={query ? "没有匹配的用户" : "暂无用户"} />,
            }}
            columns={[
              {
                title: "用户名",
                key: "username",
                width: 140,
                render: (_, u) => <code>{u.username}</code>,
              },
              {
                title: "显示名",
                dataIndex: "display_name",
                width: 120,
              },
              {
                title: "本地账号",
                key: "local_account",
                width: 96,
                render: (_, u) =>
                  u.local_account ? "是" : <Text type="secondary">否</Text>,
              },
              {
                title: "平台管理员",
                key: "platform_admin",
                width: 120,
                render: (_, u) =>
                  u.platform_admin ? (
                    <Tag className="m-0 border-0 bg-accent-soft text-accent">
                      平台管理员
                    </Tag>
                  ) : (
                    <Text type="secondary">—</Text>
                  ),
              },
              {
                title: "所在空间",
                key: "workspaces",
                render: (_, u) => {
                  if (!u.platform_admin && !u.workspaces.length) {
                    return <Text type="secondary">—</Text>;
                  }
                  return (
                    <span className="flex flex-wrap gap-1">
                      {u.platform_admin && (
                        <Tag className="m-0 border-0 bg-accent-soft text-accent">
                          全部空间（超级管理员）
                        </Tag>
                      )}
                      {u.workspaces.map((ws) => (
                        <Tag key={ws.id} className="m-0">
                          {ws.name}
                        </Tag>
                      ))}
                    </span>
                  );
                },
              },
              {
                title: "最近登录",
                key: "last_login_at",
                width: 170,
                render: (_, u) =>
                  u.last_login_at ? (
                    <span className="tabular-nums text-xs">
                      {formatLoginTime(u.last_login_at)}
                    </span>
                  ) : (
                    <Text type="secondary" className="text-xs">
                      尚未登录
                    </Text>
                  ),
              },
              {
                title: "操作",
                key: "actions",
                width: 100,
                align: "right",
                render: (_, u) => (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setDrawerError("");
                      setAddWsId(undefined);
                      setAddRole("member");
                      setDrawerUserId(u.id);
                    }}
                  >
                    分配空间
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      </PageBody>

      <Modal
        open={createOpen}
        title="新建用户"
        onCancel={() => {
          if (!createBusy) setCreateOpen(false);
        }}
        okText="创建用户"
        cancelText="取消"
        okButtonProps={{ loading: createBusy }}
        onOk={() => createForm.submit()}
        destroyOnHidden
      >
        <Text type="secondary" className="mb-3 block text-xs">
          预建用户后可立即分配空间；用户首次通过 SSO 登录时按用户名自动匹配并保留空间角色。
        </Text>
        <Form form={createForm} layout="vertical" onFinish={(v) => void handleCreateUser(v)}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, whitespace: true, message: "请填写用户名" },
              { max: 120, message: "不超过 120 个字符" },
            ]}
          >
            <Input
              aria-label="用户名"
              placeholder="例如：zhaoliu"
              autoFocus
              onChange={() => createError && setCreateError("")}
            />
          </Form.Item>
          <Form.Item
            name="display_name"
            label="显示名"
            rules={[{ required: true, whitespace: true, message: "请填写显示名" }]}
          >
            <Input aria-label="显示名" placeholder="例如：赵六" />
          </Form.Item>
          <Form.Item name="email" label="邮箱（可选）">
            <Input aria-label="邮箱（可选）" placeholder="zhaoliu@example.com" />
          </Form.Item>
          {createError && <Alert type="error" showIcon message={createError} />}
        </Form>
      </Modal>

      <Drawer
        open={!!drawerUser}
        title={
          drawerUser
            ? `分配空间 · ${drawerUser.display_name} (${drawerUser.username})`
            : "分配空间"
        }
        width={540}
        onClose={() => {
          setDrawerUserId(null);
          setDrawerError("");
        }}
      >
        {drawerUser && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between rounded-sm border border-rule bg-surface-raised px-3 py-2 text-xs">
              <span>
                用户名：<code>{drawerUser.username}</code> ·{" "}
                {drawerUser.local_account ? "本地账号" : "SSO 账号"}
              </span>
              <Text type="secondary" className="text-xs">
                {drawerUser.last_login_at
                  ? `最近登录 ${formatLoginTime(drawerUser.last_login_at)}`
                  : "尚未登录"}
              </Text>
            </div>
            {drawerUser.platform_admin && (
              <Alert
                type="info"
                showIcon
                message="平台超级管理员已自动拥有全部工作空间的管理员权限，无需写入成员表；以下仅管理显式成员记录。"
              />
            )}
            {drawerError && (
              <Alert
                type="error"
                showIcon
                message={drawerError}
                closable
                onClose={() => setDrawerError("")}
              />
            )}
            <div>
              <div className="mb-2 text-sm font-semibold text-ink">添加到工作空间</div>
              <div className="flex gap-2">
                <Select
                  aria-label="选择工作空间"
                  placeholder={
                    availableWorkspaces.length
                      ? "选择工作空间（全部空间）"
                      : "已加入全部工作空间"
                  }
                  className="min-w-0 flex-1"
                  value={addWsId}
                  disabled={drawerBusy || availableWorkspaces.length === 0}
                  onChange={setAddWsId}
                  options={availableWorkspaces.map((w) => ({
                    value: w.id,
                    label: `${w.name}（${w.is_public ? "公开" : "私有"}）`,
                  }))}
                />
                <Select
                  aria-label="分配空间角色"
                  className="w-28"
                  value={addRole}
                  disabled={drawerBusy}
                  onChange={(v) => setAddRole(v)}
                  options={ROLE_OPTIONS}
                />
                <Button
                  type="primary"
                  disabled={!addWsId}
                  loading={drawerBusy}
                  onClick={() => void handleAddWorkspace()}
                >
                  添加
                </Button>
              </div>
            </div>
            <div>
              <div className="mb-2 text-sm font-semibold text-ink">
                已加入空间（{drawerUser.workspaces.length}）
              </div>
              <Table<AdminUserWorkspace>
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={drawerUser.workspaces}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="尚未分配工作空间"
                    />
                  ),
                }}
                columns={[
                  {
                    title: "工作空间",
                    key: "ws",
                    render: (_, ws) => {
                      const info = workspaceMap.get(ws.id);
                      const isPublic = info?.is_public ?? false;
                      return (
                        <span className="inline-flex items-center gap-2">
                          <span className="font-medium text-ink">{ws.name}</span>
                          {info &&
                            (isPublic ? (
                              <Tag className="m-0 border-0 bg-accent-soft text-accent">
                                公开
                              </Tag>
                            ) : (
                              <Text type="secondary" className="text-xs">
                                私有
                              </Text>
                            ))}
                        </span>
                      );
                    },
                  },
                  {
                    title: "角色",
                    key: "role",
                    width: 132,
                    render: (_, ws) => (
                      <Select
                        size="small"
                        aria-label={`${ws.name} 角色`}
                        className="w-28"
                        value={ws.role}
                        disabled={drawerBusy}
                        onChange={(val) => void handleRoleChange(ws.id, val)}
                        options={ROLE_OPTIONS}
                      />
                    ),
                  },
                  {
                    title: "",
                    key: "remove",
                    width: 68,
                    align: "right",
                    render: (_, ws) => (
                      <Button
                        type="link"
                        size="small"
                        danger
                        disabled={drawerBusy}
                        aria-label={`移除 ${ws.name}`}
                        onClick={() => void handleRemoveWs(ws.id)}
                      >
                        移除
                      </Button>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        )}
      </Drawer>
    </PlatformFrame>
  );
}
