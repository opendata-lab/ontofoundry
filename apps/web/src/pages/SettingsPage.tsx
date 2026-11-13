import {
  Alert,
  App,
  AutoComplete,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, workspaceRequest } from "../api/client";
import type {
  DataAgentHealth,
  Member,
  WorkspaceRole,
  WorkspaceUserSearchItem,
} from "../api/types";
import { NoAccessResult } from "../components/NoAccessResult";
import {
  PageBody,
  PageHeader,
  Panel,
  PanelToolbar,
  SectionTitle,
  StatusMark,
} from "../components/layout";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ROLE_OPTIONS, useWorkspacePermissions } from "../hooks/useWorkspacePermissions";

const { Text } = Typography;

function settingsErrorText(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.code === "LAST_ADMIN") return error.message || "该空间至少需要一名管理员";
    if (error.code === "USER_NOT_FOUND") {
      return error.message || "用户不存在，请联系平台管理员在用户管理中创建";
    }
    if (error.code === "ALREADY_MEMBER") return error.message || "该用户已是空间成员";
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

export function SettingsPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const { canManage } = useWorkspacePermissions();
  const { message } = App.useApp();

  const [members, setMembers] = useState<Member[]>([]);
  const [dataagentHealth, setDataagentHealth] = useState<DataAgentHealth | null>(null);
  const [error, setError] = useState("");
  const [memberError, setMemberError] = useState("");
  const [notice, setNotice] = useState("");
  const [infoDirty, setInfoDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [publicBusy, setPublicBusy] = useState(false);
  const [publicConfirmOpen, setPublicConfirmOpen] = useState(false);

  const [searchText, setSearchText] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<WorkspaceUserSearchItem[]>([]);
  const [addRole, setAddRole] = useState<WorkspaceRole>("member");
  const [memberBusy, setMemberBusy] = useState(false);
  const searchSeq = useRef(0);

  usePageTab({ dirty: infoDirty || Boolean(searchText.trim()), busy: busy || memberBusy || publicBusy });

  const loadMembers = useCallback(
    () => api.members(workspace.id).then((r) => setMembers(r.items)),
    [workspace.id],
  );

  useEffect(() => {
    if (!canManage) return;
    loadMembers().catch((e: Error) => setError(e.message));
    workspaceRequest<DataAgentHealth>(workspace.id, "/settings/dataagent-health")
      .then(setDataagentHealth)
      .catch((e: Error) => setError(e.message));
  }, [workspace.id, canManage, loadMembers]);

  const runUserSearch = useCallback(
    async (q: string) => {
      const seq = ++searchSeq.current;
      try {
        const res = await api.searchWorkspaceUsers(workspace.id, q.trim() || undefined);
        if (seq === searchSeq.current) setSearchResults(res.items);
      } catch {
        if (seq === searchSeq.current) setSearchResults([]);
      }
    },
    [workspace.id],
  );

  const memberUserIds = useMemo(() => new Set(members.map((m) => m.user_id)), [members]);

  const autoOptions = useMemo(
    () =>
      searchResults.map((u) => {
        const already = memberUserIds.has(u.id);
        return {
          value: u.username,
          user: u,
          disabled: already,
          label: (
            <div className="flex items-center justify-between gap-2">
              <span>
                <code className="mr-1.5">{u.username}</code>
                <span>{u.display_name}</span>
              </span>
              {already ? (
                <Text type="secondary" className="text-xs">
                  已是成员
                </Text>
              ) : !u.last_login_at ? (
                <Tag className="m-0">尚未登录</Tag>
              ) : null}
            </div>
          ),
        };
      }),
    [searchResults, memberUserIds],
  );

  if (!canManage) {
    return (
      <div className="flex h-full min-h-0 flex-col bg-canvas">
        <NoAccessResult subtitle="只有该工作空间的管理员可以打开「空间设置」。" />
      </div>
    );
  }

  const updatePublic = async (isPublic: boolean) => {
    setPublicBusy(true);
    setError("");
    try {
      await api.updateWorkspace(workspace.id, { is_public: isPublic });
      refresh();
      void message.success(
        isPublic ? `「${workspace.name}」已设为公开空间` : "已设为私有空间，非成员将无法访问",
      );
    } catch (e) {
      setError(settingsErrorText(e, "更新空间公开状态失败"));
    } finally {
      setPublicBusy(false);
    }
  };

  const handleSwitchChange = (checked: boolean) => {
    if (checked) {
      setPublicConfirmOpen(true);
    } else {
      void updatePublic(false);
    }
  };

  const handleMemberRoleChange = async (memberId: Member["id"], role: WorkspaceRole) => {
    setMemberError("");
    setMemberBusy(true);
    try {
      await api.updateMemberRole(workspace.id, memberId, role);
      await loadMembers();
      void message.success("成员角色已更新");
    } catch (e) {
      const msg = settingsErrorText(e, "更新成员角色失败");
      setMemberError(msg);
      void message.error(msg);
    } finally {
      setMemberBusy(false);
    }
  };

  const handleRemoveMember = async (memberId: Member["id"]) => {
    setMemberError("");
    setMemberBusy(true);
    try {
      await api.removeMember(workspace.id, memberId);
      await loadMembers();
      void message.success("已移除成员");
    } catch (e) {
      const msg = settingsErrorText(e, "移除成员失败");
      setMemberError(msg);
      void message.error(msg);
    } finally {
      setMemberBusy(false);
    }
  };

  const handleAddMember = async () => {
    setMemberError("");
    const trimmed = searchText.trim();
    if (!trimmed && !selectedUserId) {
      setMemberError("请输入并选择已有用户");
      return;
    }
    let target =
      (selectedUserId && searchResults.find((u) => u.id === selectedUserId)) ||
      searchResults.find((u) => u.username.toLowerCase() === trimmed.toLowerCase());

    if (!target && trimmed) {
      setMemberBusy(true);
      try {
        const res = await api.searchWorkspaceUsers(workspace.id, trimmed);
        setSearchResults(res.items);
        target = res.items.find((u) => u.username.toLowerCase() === trimmed.toLowerCase());
      } catch (e) {
        setMemberError(settingsErrorText(e, "查询用户失败"));
        setMemberBusy(false);
        return;
      }
      setMemberBusy(false);
    }

    if (!target) {
      setMemberError("用户不存在，请联系平台管理员在用户管理中创建");
      return;
    }
    if (memberUserIds.has(target.id)) {
      setMemberError("该用户已是空间成员");
      return;
    }

    setMemberBusy(true);
    try {
      await api.addMember(workspace.id, { user_id: target.id, role: addRole });
      await loadMembers();
      setSearchText("");
      setSelectedUserId(null);
      setAddRole("member");
      void message.success(`已添加成员 ${target.display_name} (${target.username})`);
    } catch (e) {
      setMemberError(settingsErrorText(e, "添加成员失败"));
    } finally {
      setMemberBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="空间设置" />
      <PageBody>
        {error && (
          <Alert
            type="error"
            showIcon
            message={error}
            closable={{ closeIcon: true, "aria-label": "关闭错误" }}
            onClose={() => setError("")}
          />
        )}
        <Panel className="w-full max-w-settings">
          <PanelToolbar>
            <SectionTitle title="空间信息" />
          </PanelToolbar>
          <div className="p-4">
            <Form
              layout="vertical"
              initialValues={{ name: workspace.name, description: workspace.description }}
              onValuesChange={() => setInfoDirty(true)}
              onFinish={(values: { name: string; description: string }) => {
                setBusy(true);
                api
                  .updateWorkspace(workspace.id, values)
                  .then(() => {
                    refresh();
                    setNotice("空间信息已保存");
                    setInfoDirty(false);
                  })
                  .catch((e: Error) => setError(e.message))
                  .finally(() => setBusy(false));
              }}
            >
              <Form.Item name="name" label="空间名称" rules={[{ required: true, message: "请填写空间名称" }]}>
                <Input aria-label="空间名称" />
              </Form.Item>
              <Form.Item name="description" label="说明">
                <Input.TextArea aria-label="说明" rows={3} />
              </Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={busy}>
                  保存空间信息
                </Button>
                {notice && (
                  <span role="status">
                    <StatusMark state="mapped" label={notice} />
                  </span>
                )}
              </Space>
            </Form>
          </div>
        </Panel>
        <Panel className="w-full max-w-settings">
          <PanelToolbar>
            <SectionTitle
              title="空间公开"
              note={workspace.is_public ? "当前为公开空间" : "当前为私有空间"}
            />
          </PanelToolbar>
          <div className="flex items-start justify-between gap-4 p-4">
            <div className="flex flex-col gap-1">
              <strong className="text-sm text-ink">对平台全部登录用户公开</strong>
              <Text type="secondary" className="text-xs">
                所有登录用户可阅读本空间全部内容（本体、映射、材料、会话和实例），但不能修改；关闭后改为私有，对非成员完全不可见。
              </Text>
            </div>
            <Switch
              aria-label="对平台全部登录用户公开"
              checked={workspace.is_public}
              loading={publicBusy}
              checkedChildren="公开"
              unCheckedChildren="私有"
              onChange={handleSwitchChange}
            />
          </div>
        </Panel>
        <Panel className="w-full max-w-settings">
          <PanelToolbar>
            <SectionTitle title="空间成员" note={`${members.length} 人`} />
          </PanelToolbar>
          <Text type="secondary" className="block px-4 py-3 text-xs">
            {workspace.is_public
              ? "空间已公开，所有登录用户均可阅读全部内容；空间成员按可查看 / 可编辑 / 管理员赋权（平台超级管理员可管理全部空间）。"
              : "空间为私有，仅以下成员及平台超级管理员可访问本空间内容（按可查看 / 可编辑 / 管理员赋权）。"}
          </Text>
          {memberError && (
            <div className="px-4 pb-3">
              <Alert
                type="error"
                showIcon
                message={memberError}
                closable={{ closeIcon: true, "aria-label": "关闭成员错误" }}
                onClose={() => setMemberError("")}
              />
            </div>
          )}
          <Table<Member>
            size="middle"
            onHeaderRow={() => ({ className: "text-xs" })}
            rowKey="id"
            pagination={false}
            dataSource={members}
            columns={[
              {
                title: "用户",
                key: "display_name",
                render: (_, m) => (
                  <span className="inline-flex items-center gap-2">
                    <span className="font-medium text-ink">{m.display_name}</span>
                    {!m.last_login_at && <Tag className="m-0">尚未登录</Tag>}
                  </span>
                ),
              },
              {
                title: "用户名",
                key: "username",
                render: (_, m) => <code>{m.username}</code>,
              },
              {
                title: "角色",
                key: "role",
                width: 140,
                render: (_, m) => (
                  <Select
                    size="small"
                    aria-label={`${m.display_name} 角色`}
                    className="w-28"
                    value={m.role}
                    disabled={memberBusy}
                    onChange={(val) => void handleMemberRoleChange(m.id, val)}
                    options={ROLE_OPTIONS}
                  />
                ),
              },
              {
                title: "",
                key: "action",
                width: 80,
                align: "right",
                render: (_, m) => (
                  <Button
                    size="small"
                    type="link"
                    danger
                    disabled={memberBusy}
                    aria-label={`移除 ${m.display_name}`}
                    onClick={() => void handleRemoveMember(m.id)}
                  >
                    移除
                  </Button>
                ),
              },
            ]}
          />
          <div className="flex flex-wrap items-center gap-2 border-t border-rule p-4">
            <AutoComplete
              className="w-80"
              value={searchText}
              options={autoOptions}
              allowClear
              notFoundContent={
                <div className="px-2 py-1.5 text-xs text-danger">
                  用户不存在，请联系平台管理员在用户管理中创建
                </div>
              }
              onFocus={() => void runUserSearch(searchText)}
              onSearch={(val) => {
                setSearchText(val);
                setSelectedUserId(null);
                setMemberError("");
                void runUserSearch(val);
              }}
              onChange={(val) => {
                setSearchText(val ?? "");
                if (!val) setSelectedUserId(null);
              }}
              onSelect={(val, opt) => {
                setSearchText(val);
                setSelectedUserId(opt.user ? opt.user.id : null);
                setMemberError("");
              }}
            >
              <Input
                aria-label="搜索已有用户"
                placeholder="按用户名搜索已有用户（如 lisi）"
                prefix={<Search size={14} className="text-muted" />}
                onPressEnter={(e) => {
                  if (!selectedUserId) {
                    e.preventDefault();
                    void handleAddMember();
                  }
                }}
              />
            </AutoComplete>
            <Select
              aria-label="成员角色"
              className="w-28"
              value={addRole}
              disabled={memberBusy}
              onChange={(val) => setAddRole(val)}
              options={ROLE_OPTIONS}
            />
            <Button type="primary" loading={memberBusy} onClick={() => void handleAddMember()}>
              添加成员
            </Button>
          </div>
        </Panel>
        <Panel className="w-full max-w-settings">
          <PanelToolbar>
            <SectionTitle title="DataAgent 连通性" />
          </PanelToolbar>
          <Text type="secondary" className="block px-4 py-3 text-xs">
            配置检查。地址、站点与凭据均由部署环境和 DataAgent 管理端配置。
          </Text>
          {dataagentHealth ? (
            <Table
              size="middle"
              onHeaderRow={() => ({ className: "text-xs" })}
              rowKey="name"
              pagination={false}
              dataSource={dataagentHealth.checks}
              columns={[
                { title: "检查项", dataIndex: "name", width: 180 },
                {
                  title: "状态",
                  key: "ok",
                  width: 90,
                  render: (_, check) => (
                    <StatusMark state={check.ok ? "mapped" : "error"} label={check.ok ? "通过" : "需处理"} />
                  ),
                },
                {
                  title: "结果与修复指引",
                  key: "message",
                  render: (_, check) => (
                    <div className="flex flex-col">
                      <span>{check.message}</span>
                      {check.hint && <Text type="secondary">{check.hint}</Text>}
                    </div>
                  ),
                },
              ]}
            />
          ) : (
            <div className="p-4">
              <Spin />
            </div>
          )}
        </Panel>
      </PageBody>
      <Modal
        open={publicConfirmOpen}
        title={`确认将「${workspace.name}」设为公开？`}
        okText="确认公开"
        cancelText="取消"
        okButtonProps={{ loading: publicBusy }}
        onCancel={() => {
          if (!publicBusy) setPublicConfirmOpen(false);
        }}
        onOk={() => {
          void updatePublic(true).then(() => setPublicConfirmOpen(false));
        }}
      >
        <p className="m-0 text-sm leading-base text-ink-2">
          开启公开后，所有登录用户都能在工作空间目录中看到本空间，并可阅读本空间的映射、材料、会话和实例数据（包含业务库实例查询），但不能修改任何内容。
        </p>
      </Modal>
    </div>
  );
}
