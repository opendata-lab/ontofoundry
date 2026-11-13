import {
  Alert,
  App,
  Button,
  Checkbox,
  Descriptions,
  Empty,
  Form,
  Input,
  type InputRef,
  Modal,
  Popconfirm,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ArrowLeft, Check, Copy, Pencil, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type {
  CreatedPersonalToken,
  MeWorkspace,
  PersonalToken,
  TokenPermission,
  User,
} from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { PlatformFrame } from "../components/PlatformFrame";
import {
  PageBody,
  PageTabs,
  PageToolbar,
  Panel,
  PanelToolbar,
  SectionTitle,
} from "../components/layout";
import { ROLE_LABELS } from "../hooks/useWorkspacePermissions";
import { copyText } from "../lib/clipboard";

const { Text } = Typography;

type CreateTokenValues = {
  name: string;
  includeMappings?: boolean;
};

function formatTokenTime(iso: string) {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function tokenErrorText(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message || fallback;
  return error instanceof Error ? error.message : fallback;
}

async function copyTokenToClipboard(
  token: string,
  inputEl: HTMLInputElement | null,
): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(token);
      return true;
    } catch {
      // Fall through to execCommand fallback in non-secure (HTTP) contexts.
    }
  }
  if (inputEl) {
    inputEl.focus();
    inputEl.select();
    inputEl.setSelectionRange?.(0, token.length);
    if (typeof document.execCommand === "function") {
      try {
        if (document.execCommand("copy")) return true;
      } catch {
        // Fall through to shared clipboard helper.
      }
    }
  }
  try {
    await copyText(token);
    return true;
  } catch {
    return false;
  }
}

/** Personal profile (/me) and personal access tokens (/me/tokens). */
export function MePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = App.useApp();
  const activeTab =
    location.pathname.replace(/\/$/, "") === "/me/tokens" ? "tokens" : "profile";

  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<MeWorkspace[]>([]);
  const [error, setError] = useState("");

  const [tokens, setTokens] = useState<PersonalToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokensError, setTokensError] = useState("");
  const tokenRequestSeq = useRef(0);

  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [editingPermId, setEditingPermId] = useState<string | null>(null);
  const [editMappings, setEditMappings] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");
  const [createdToken, setCreatedToken] = useState<CreatedPersonalToken | null>(null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const [createForm] = Form.useForm<CreateTokenValues>();
  const tokenInputRef = useRef<InputRef>(null);

  const loadProfile = useCallback(() => {
    setError("");
    Promise.all([api.me(), api.meWorkspaces()])
      .then(([u, ws]) => {
        setUser(u);
        setWorkspaces(ws.items);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const loadTokens = useCallback(async () => {
    const seq = ++tokenRequestSeq.current;
    setTokensLoading(true);
    setTokensError("");
    try {
      const res = await api.tokens();
      if (seq === tokenRequestSeq.current) setTokens(res.items);
    } catch (e) {
      if (seq === tokenRequestSeq.current) {
        setTokensError(tokenErrorText(e, "加载个人令牌失败"));
      }
    } finally {
      if (seq === tokenRequestSeq.current) setTokensLoading(false);
    }
  }, []);

  useEffect(loadProfile, [loadProfile]);

  useEffect(() => {
    if (!user || activeTab !== "tokens") return;
    void loadTokens();
  }, [user, activeTab, loadTokens]);

  if (error) return <ErrorSurface message={error} retry={loadProfile} />;
  if (!user) return <LoadingSurface label="正在读取个人中心…" />;

  const startRename = (token: PersonalToken) => {
    setEditingPermId(null);
    setRenamingId(token.id);
    setRenameValue(token.name);
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
  };

  const saveRename = async (token: PersonalToken) => {
    const trimmed = renameValue.trim();
    if (!trimmed) {
      void message.error("令牌名称不能为空");
      return;
    }
    if (trimmed.length > 100) {
      void message.error("令牌名称不能超过 100 个字符");
      return;
    }
    if (trimmed === token.name) {
      cancelRename();
      return;
    }
    setSavingId(token.id);
    try {
      const updated = await api.updateToken(token.id, { name: trimmed });
      setTokens((prev) => prev.map((t) => (t.id === token.id ? updated : t)));
      cancelRename();
      void message.success("令牌名称已更新");
    } catch (e) {
      void message.error(tokenErrorText(e, "更新令牌名称失败"));
    } finally {
      setSavingId(null);
    }
  };

  const startEditPermissions = (token: PersonalToken) => {
    setRenamingId(null);
    setEditingPermId(token.id);
    setEditMappings(token.permissions.includes("mappings:read"));
  };

  const cancelEditPermissions = () => {
    setEditingPermId(null);
  };

  const savePermissions = async (token: PersonalToken) => {
    const permissions: TokenPermission[] = editMappings
      ? ["ontology:read", "mappings:read"]
      : ["ontology:read"];
    setSavingId(token.id);
    try {
      const updated = await api.updateToken(token.id, { permissions });
      setTokens((prev) => prev.map((t) => (t.id === token.id ? updated : t)));
      setEditingPermId(null);
      void message.success("令牌权限已更新");
    } catch (e) {
      void message.error(tokenErrorText(e, "更新令牌权限失败"));
    } finally {
      setSavingId(null);
    }
  };

  const handleRevoke = async (token: PersonalToken) => {
    setRevokingId(token.id);
    try {
      await api.revokeToken(token.id);
      setTokens((prev) => prev.filter((t) => t.id !== token.id));
      void message.success(`已撤销令牌「${token.name}」`);
    } catch (e) {
      void message.error(tokenErrorText(e, "撤销令牌失败"));
    } finally {
      setRevokingId(null);
    }
  };

  const openCreateModal = () => {
    setCreateError("");
    setCreatedToken(null);
    setCopyStatus("idle");
    createForm.resetFields();
    setCreateOpen(true);
  };

  const closeCreateModal = () => {
    if (createBusy) return;
    setCreateOpen(false);
    setCreatedToken(null);
    setCopyStatus("idle");
    setCreateError("");
    createForm.resetFields();
  };

  const handleCreateToken = async (values: CreateTokenValues) => {
    const name = values.name.trim();
    const permissions: TokenPermission[] = values.includeMappings
      ? ["ontology:read", "mappings:read"]
      : ["ontology:read"];
    setCreateBusy(true);
    setCreateError("");
    try {
      const created = await api.createToken({ name, permissions });
      setCreatedToken(created);
      setCopyStatus("idle");
      await loadTokens();
    } catch (e) {
      setCreateError(tokenErrorText(e, "新建令牌失败"));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleCopyToken = async () => {
    if (!createdToken) return;
    const ok = await copyTokenToClipboard(
      createdToken.token,
      tokenInputRef.current?.input ?? null,
    );
    if (ok) {
      setCopyStatus("copied");
      void message.success("已复制个人令牌");
    } else {
      setCopyStatus("failed");
      tokenInputRef.current?.input?.focus();
      tokenInputRef.current?.input?.select();
    }
  };

  const tokenColumns: ColumnsType<PersonalToken> = [
    {
      title: "名称",
      key: "name",
      render: (_, token) =>
        renamingId === token.id ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <Input
              size="small"
              aria-label="令牌名称"
              className="w-44"
              maxLength={100}
              value={renameValue}
              disabled={savingId === token.id}
              onChange={(e) => setRenameValue(e.target.value)}
              onPressEnter={() => void saveRename(token)}
            />
            <Button
              size="small"
              type="primary"
              aria-label="保存名称"
              loading={savingId === token.id}
              onClick={() => void saveRename(token)}
            >
              保存
            </Button>
            <Button
              size="small"
              aria-label="取消重命名"
              disabled={savingId === token.id}
              onClick={cancelRename}
            >
              取消
            </Button>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <span className="font-medium text-ink">{token.name}</span>
            <Button
              type="text"
              size="small"
              aria-label={`重命名 ${token.name}`}
              icon={<Pencil size={13} />}
              onClick={() => startRename(token)}
            />
          </span>
        ),
    },
    {
      title: "权限",
      key: "permissions",
      render: (_, token) =>
        editingPermId === token.id ? (
          <span className="flex flex-wrap items-center gap-2">
            <Checkbox checked disabled>
              读取语义
            </Checkbox>
            <Checkbox
              aria-label="读取映射"
              checked={editMappings}
              disabled={savingId === token.id}
              onChange={(e) => setEditMappings(e.target.checked)}
            >
              读取映射
            </Checkbox>
            <Button
              size="small"
              type="primary"
              aria-label="保存权限"
              loading={savingId === token.id}
              onClick={() => void savePermissions(token)}
            >
              保存
            </Button>
            <Button
              size="small"
              aria-label="取消编辑权限"
              disabled={savingId === token.id}
              onClick={cancelEditPermissions}
            >
              取消
            </Button>
          </span>
        ) : (
          <span className="flex flex-wrap items-center gap-1.5">
            <Tag className="m-0 border-0 bg-accent-soft text-accent">读取语义</Tag>
            {token.permissions.includes("mappings:read") && (
              <Tag className="m-0 border-0 bg-success-soft text-success">读取映射</Tag>
            )}
            <Button
              type="link"
              size="small"
              aria-label={`编辑 ${token.name} 权限`}
              onClick={() => startEditPermissions(token)}
            >
              编辑
            </Button>
          </span>
        ),
    },
    {
      title: "创建时间",
      key: "created_at",
      width: 170,
      render: (_, token) => (
        <span className="tabular-nums text-xs whitespace-nowrap">
          {formatTokenTime(token.created_at)}
        </span>
      ),
    },
    {
      title: "最近使用",
      key: "last_used_at",
      width: 170,
      render: (_, token) =>
        token.last_used_at ? (
          <span className="tabular-nums text-xs whitespace-nowrap">
            {formatTokenTime(token.last_used_at)}
          </span>
        ) : (
          <Text type="secondary" className="text-xs">
            —
          </Text>
        ),
    },
    {
      title: "操作",
      key: "actions",
      width: 84,
      align: "right",
      render: (_, token) => (
        <Popconfirm
          title="撤销个人令牌？"
          description={`撤销后「${token.name}」将立即失效，使用该令牌的客户端需要重新配置。`}
          okText="确认撤销"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => void handleRevoke(token)}
        >
          <Button
            type="link"
            size="small"
            danger
            loading={revokingId === token.id}
            aria-label={`撤销 ${token.name}`}
          >
            撤销
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <PlatformFrame user={user}>
      <PageTabs
        title="个人中心"
        note="查看本人账号与空间成员身份，或签发外部智能体网关个人令牌。"
        actions={
          <Button icon={<ArrowLeft size={14} />} onClick={() => navigate("/")}>
            返回工作空间
          </Button>
        }
        activeKey={activeTab}
        onChange={(key) => navigate(key === "tokens" ? "/me/tokens" : "/me")}
        items={[
          {
            key: "profile",
            label: "个人信息",
            children: (
              <PageBody>
                <Panel className="mx-auto w-full max-w-settings">
                  <PanelToolbar>
                    <SectionTitle title="个人信息" />
                  </PanelToolbar>
                  <div className="p-4">
                    <Descriptions column={2} size="small" colon={false}>
                      <Descriptions.Item label="用户名">
                        <code>{user.username}</code>
                      </Descriptions.Item>
                      <Descriptions.Item label="显示名">{user.display_name}</Descriptions.Item>
                      <Descriptions.Item label="邮箱">
                        {user.email || <Text type="secondary">—</Text>}
                      </Descriptions.Item>
                      <Descriptions.Item label="本地账号">
                        {user.local_account ? "是" : "否"}
                      </Descriptions.Item>
                    </Descriptions>
                  </div>
                </Panel>
                <Panel className="mx-auto w-full max-w-settings">
                  <PanelToolbar
                    extra={
                      user.is_platform_admin ? (
                        <Tag className="m-0 border-0 bg-accent-soft text-accent">
                          全部空间（超级管理员）
                        </Tag>
                      ) : null
                    }
                  >
                    <SectionTitle
                      title="所在空间及角色"
                      note={
                        user.is_platform_admin
                          ? `超级管理员可管理全部空间 · 成员记录 ${workspaces.length} 条`
                          : `${workspaces.length} 个已加入的工作空间`
                      }
                    />
                  </PanelToolbar>
                  <Table<MeWorkspace>
                    size="middle"
                    rowKey="id"
                    pagination={false}
                    dataSource={workspaces}
                    onHeaderRow={() => ({ className: "text-xs" })}
                    locale={{
                      emptyText: (
                        <Empty description="暂未加入任何工作空间，请联系空间管理员或平台管理员分配。" />
                      ),
                    }}
                    columns={[
                      {
                        title: "工作空间",
                        key: "name",
                        render: (_, ws) => (
                          <span className="inline-flex items-center gap-2">
                            <strong className="text-ink">{ws.name}</strong>
                            {ws.is_public && (
                              <Tag className="m-0 border-0 bg-accent-soft text-accent">公开</Tag>
                            )}
                          </span>
                        ),
                      },
                      {
                        title: "空间角色",
                        key: "role",
                        width: 140,
                        render: (_, ws) => (
                          <Tag
                            className={
                              ws.role === "admin"
                                ? "m-0 border-0 bg-accent-soft text-accent"
                                : "m-0 border-rule bg-surface-soft text-ink-2"
                            }
                          >
                            {ROLE_LABELS[ws.role] ?? ws.role}
                          </Tag>
                        ),
                      },
                      {
                        title: "",
                        key: "enter",
                        width: 110,
                        align: "right",
                        render: (_, ws) => (
                          <Button
                            type="link"
                            size="small"
                            onClick={() => navigate(`/workspaces/${ws.id}/view`)}
                          >
                            进入空间
                          </Button>
                        ),
                      },
                    ]}
                  />
                </Panel>
              </PageBody>
            ),
          },
          {
            key: "tokens",
            label: "个人令牌",
            children: (
              <PageBody>
                <div className="mx-auto flex w-full max-w-settings flex-col gap-4">
                  <PageToolbar
                    extra={
                      <Text type="secondary" className="text-xs">
                        {tokens.length} 个有效令牌 · 永不过期，可随时撤销
                      </Text>
                    }
                  >
                    <Button
                      type="primary"
                      icon={<Plus size={14} />}
                      onClick={openCreateModal}
                    >
                      新建令牌
                    </Button>
                  </PageToolbar>
                  {tokensError && (
                    <Alert
                      type="error"
                      showIcon
                      message={tokensError}
                      action={
                        <Button size="small" onClick={() => void loadTokens()}>
                          重试
                        </Button>
                      }
                    />
                  )}
                  <Panel>
                    <Table<PersonalToken>
                      size="middle"
                      rowKey="id"
                      loading={tokensLoading}
                      pagination={false}
                      dataSource={tokens}
                      onHeaderRow={() => ({ className: "text-xs whitespace-nowrap" })}
                      locale={{
                        emptyText: (
                          <Empty description="暂无个人令牌，点击「新建令牌」签发后即可在外部智能体中使用。" />
                        ),
                      }}
                      columns={tokenColumns}
                    />
                  </Panel>
                </div>
              </PageBody>
            ),
          },
        ]}
      />
      <Modal
        open={createOpen}
        title={createdToken ? "令牌已生成" : "新建令牌"}
        maskClosable={!createdToken}
        onCancel={closeCreateModal}
        destroyOnHidden
        footer={
          createdToken ? (
            <Button type="primary" onClick={closeCreateModal}>
              我已保存，关闭
            </Button>
          ) : undefined
        }
        okText="生成令牌"
        cancelText="取消"
        okButtonProps={{ loading: createBusy }}
        onOk={createdToken ? undefined : () => createForm.submit()}
      >
        {createdToken ? (
          <div className="flex flex-col gap-3">
            <Alert
              type="warning"
              showIcon
              message="令牌仅在本次弹窗显示，关闭后将无法再次查看"
              description="请将该令牌写入外部智能体客户端的 MCP 配置（如环境变量 ONTOFOUNDRY_TOKEN 或插件敏感设置），不要直接粘贴到对话中。"
            />
            <div className="flex items-center gap-2">
              <Input
                ref={tokenInputRef}
                readOnly
                aria-label="生成的个人令牌"
                value={createdToken.token}
                className="font-mono text-xs"
                onFocus={(e) => e.target.select()}
              />
              <Button
                type="primary"
                icon={copyStatus === "copied" ? <Check size={14} /> : <Copy size={14} />}
                onClick={() => void handleCopyToken()}
              >
                {copyStatus === "copied" ? "已复制" : "复制令牌"}
              </Button>
            </div>
            {copyStatus === "failed" && (
              <Text type="warning" className="text-xs">
                当前浏览器限制自动复制，请直接手动复制上方文本框中的令牌。
              </Text>
            )}
          </div>
        ) : (
          <Form
            form={createForm}
            layout="vertical"
            onFinish={(v) => void handleCreateToken(v)}
          >
            <Form.Item
              name="name"
              label="令牌名称"
              rules={[
                { required: true, whitespace: true, message: "请填写令牌名称" },
                { max: 100, message: "不超过 100 个字符" },
              ]}
            >
              <Input
                aria-label="令牌名称"
                placeholder="例如：办公电脑"
                maxLength={100}
                autoFocus
                onChange={() => createError && setCreateError("")}
              />
            </Form.Item>
            <div className="mb-3 flex flex-col gap-2">
              <div className="text-sm text-ink">权限</div>
              <Checkbox checked disabled>
                读取语义（ontology:read，必选）
              </Checkbox>
              <Form.Item name="includeMappings" valuePropName="checked" className="mb-0">
                <Checkbox>包含读取映射（mappings:read）</Checkbox>
              </Form.Item>
            </div>
            {createError && <Alert type="error" showIcon message={createError} />}
          </Form>
        )}
      </Modal>
    </PlatformFrame>
  );
}
