import {
  Alert,
  App,
  AutoComplete,
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Skeleton,
  Switch,
  Table,
  Typography,
} from "antd";
import { Plus, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { Member, WorkspaceRole, WorkspaceUserSearchItem } from "../api/types";
import { NoAccessResult } from "../components/NoAccessResult";
import {
  FormRow,
  PageBody,
  PageHeader,
  Panel,
  PanelToolbar,
  SectionTitle,
  StatusMark,
} from "../components/layout";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ROLE_OPTIONS, useWorkspacePermissions } from "../hooks/useWorkspacePermissions";
import { copyText } from "../lib/clipboard";

const { Text } = Typography;

const USER_NOT_FOUND_TEXT = "用户不存在，请联系平台管理员在用户管理中创建";

type InfoValues = { name: string; description: string };

function settingsErrorText(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.code === "LAST_ADMIN") return error.message || "该空间至少需要一名管理员";
    if (error.code === "USER_NOT_FOUND") return error.message || USER_NOT_FOUND_TEXT;
    if (error.code === "ALREADY_MEMBER") return error.message || "该用户已是空间成员";
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

export function SettingsPage() {
  const { workspace, user, refresh } = useWorkspaceContext();
  const { canManage } = useWorkspacePermissions();
  const { message } = App.useApp();
  const [form] = Form.useForm<InfoValues>();

  // Space info form state.
  const [infoDirty, setInfoDirtyState] = useState(false);
  // Read by the workspace sync below without re-running it when dirty flips,
  // so clearing dirty after a save does not copy back the not-yet-refreshed values.
  const infoDirtyRef = useRef(false);
  const setInfoDirty = useCallback((dirty: boolean) => {
    infoDirtyRef.current = dirty;
    setInfoDirtyState(dirty);
  }, []);
  const [savingInfo, setSavingInfo] = useState(false);
  const [infoSaved, setInfoSaved] = useState(false);

  // Public visibility state.
  const [publicBusy, setPublicBusy] = useState(false);
  const [publicConfirmOpen, setPublicConfirmOpen] = useState(false);

  // Member list state.
  const [members, setMembers] = useState<Member[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [membersLoadError, setMembersLoadError] = useState("");
  const [memberBusy, setMemberBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<Member["id"] | null>(null);

  // Inline add-member bar; local only, so it never marks the page tab dirty.
  const [addOpen, setAddOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<WorkspaceUserSearchItem[]>([]);
  const [searchError, setSearchError] = useState("");
  // Enter belongs to the dropdown while it shows options (it picks the highlighted one).
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [addRole, setAddRole] = useState<WorkspaceRole>("member");
  const [addBusy, setAddBusy] = useState(false);
  const [addError, setAddError] = useState("");
  const searchSeq = useRef(0);

  // Floating errors for save, visibility, role change and removal.
  const [actionError, setActionError] = useState("");
  useErrorMessage(actionError);

  usePageTab({
    dirty: infoDirty,
    busy: savingInfo || publicBusy || memberBusy || addBusy || deletingId !== null,
  });

  // Follow workspace refreshes unless the user has unsaved edits.
  useEffect(() => {
    if (!infoDirtyRef.current) {
      form.setFieldsValue({ name: workspace.name, description: workspace.description });
    }
  }, [form, workspace.name, workspace.description]);

  const loadMembers = useCallback(
    () => api.members(workspace.id).then((r) => setMembers(r.items)),
    [workspace.id],
  );

  const reloadMembers = useCallback(() => {
    setLoadingMembers(true);
    setMembersLoadError("");
    loadMembers()
      .catch((e: unknown) => setMembersLoadError(settingsErrorText(e, "加载空间成员失败")))
      .finally(() => setLoadingMembers(false));
  }, [loadMembers]);

  useEffect(() => {
    if (canManage) reloadMembers();
  }, [canManage, reloadMembers]);

  const runUserSearch = useCallback(
    async (q: string) => {
      const seq = ++searchSeq.current;
      try {
        const res = await api.searchWorkspaceUsers(workspace.id, q.trim() || undefined);
        if (seq === searchSeq.current) {
          setSearchResults(res.items);
          setSearchError("");
        }
      } catch (e) {
        if (seq === searchSeq.current) {
          setSearchResults([]);
          setSearchError(settingsErrorText(e, "搜索用户失败"));
        }
      }
    },
    [workspace.id],
  );

  const memberUserIds = useMemo(() => new Set(members.map((m) => m.user_id)), [members]);

  const autoOptions = useMemo(
    () =>
      searchResults.map((u) => {
        const already = memberUserIds.has(u.id);
        const suffix = already ? "已是成员" : !u.last_login_at ? "尚未登录" : "";
        return {
          value: u.username,
          user: u,
          disabled: already,
          label: (
            <div className="flex items-center justify-between gap-2">
              <span>{u.username}</span>
              {suffix && <span className="text-xs text-muted">{suffix}</span>}
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

  const resetInfo = () => {
    form.setFieldsValue({ name: workspace.name, description: workspace.description });
    form.setFields([{ name: "name", errors: [] }]);
    setInfoDirty(false);
  };

  const saveInfo = async (values: InfoValues) => {
    setActionError("");
    setSavingInfo(true);
    try {
      const saved = { name: values.name.trim(), description: values.description ?? "" };
      await api.updateWorkspace(workspace.id, saved);
      // Show what was stored until the workspace refresh catches up.
      form.setFieldsValue(saved);
      setInfoDirty(false);
      setInfoSaved(true);
      refresh();
    } catch (e) {
      setActionError(settingsErrorText(e, "保存空间信息失败"));
    } finally {
      setSavingInfo(false);
    }
  };

  const copySlug = async () => {
    setActionError("");
    try {
      await copyText(workspace.slug);
      void message.success("已复制空间标识");
    } catch (e) {
      setActionError(settingsErrorText(e, "复制失败"));
    }
  };

  const updatePublic = async (isPublic: boolean) => {
    setActionError("");
    setPublicBusy(true);
    try {
      await api.updateWorkspace(workspace.id, { is_public: isPublic });
      refresh();
      void message.success(
        isPublic ? `「${workspace.name}」已设为公开空间` : "已设为私有空间，非成员将无法访问",
      );
      return true;
    } catch (e) {
      setActionError(settingsErrorText(e, "更新空间公开状态失败"));
      return false;
    } finally {
      setPublicBusy(false);
    }
  };

  const handleSwitchChange = (checked: boolean) => {
    if (checked) setPublicConfirmOpen(true);
    else void updatePublic(false);
  };

  const handleMemberRoleChange = async (memberId: Member["id"], role: WorkspaceRole) => {
    setActionError("");
    setMemberBusy(true);
    try {
      await api.updateMemberRole(workspace.id, memberId, role);
      await loadMembers();
      void message.success("成员角色已更新");
    } catch (e) {
      setActionError(settingsErrorText(e, "更新成员角色失败"));
    } finally {
      setMemberBusy(false);
    }
  };

  const handleRemoveMember = async (memberId: Member["id"]) => {
    setActionError("");
    setDeletingId(memberId);
    try {
      await api.removeMember(workspace.id, memberId);
      await loadMembers();
      void message.success("已移除成员");
    } catch (e) {
      setActionError(settingsErrorText(e, "移除成员失败"));
    } finally {
      setDeletingId(null);
    }
  };

  const closeAddBar = () => {
    searchSeq.current += 1;
    setAddOpen(false);
    setSearchText("");
    setSelectedUserId(null);
    setSearchResults([]);
    setSearchError("");
    setSuggestionsOpen(false);
    setAddRole("member");
    setAddError("");
  };

  const handleAddMember = async () => {
    setAddError("");
    const trimmed = searchText.trim();
    if (!trimmed && !selectedUserId) {
      setAddError("请输入并选择已有用户");
      return;
    }
    setAddBusy(true);
    try {
      let target =
        (selectedUserId && searchResults.find((u) => u.id === selectedUserId)) ||
        searchResults.find((u) => u.username.toLowerCase() === trimmed.toLowerCase());
      if (!target && trimmed) {
        const res = await api.searchWorkspaceUsers(workspace.id, trimmed);
        setSearchResults(res.items);
        target = res.items.find((u) => u.username.toLowerCase() === trimmed.toLowerCase());
      }
      if (!target) {
        setAddError(USER_NOT_FOUND_TEXT);
        return;
      }
      if (memberUserIds.has(target.id)) {
        setAddError("该用户已是空间成员");
        return;
      }
      await api.addMember(workspace.id, { user_id: target.id, role: addRole });
      await loadMembers();
      void message.success(`已添加成员 ${target.username}`);
      closeAddBar();
    } catch (e) {
      setAddError(settingsErrorText(e, "添加成员失败"));
    } finally {
      setAddBusy(false);
    }
  };

  const rowLocked = memberBusy || deletingId !== null;

  const membersContent = loadingMembers ? (
    <div className="p-4">
      <Skeleton active title={false} paragraph={{ rows: 3 }} />
    </div>
  ) : membersLoadError ? (
    <div className="p-4">
      <Alert
        type="error"
        showIcon
        message={membersLoadError}
        action={
          <Button size="small" onClick={reloadMembers}>
            重试
          </Button>
        }
      />
    </div>
  ) : (
    <Table<Member>
      size="middle"
      onHeaderRow={() => ({ className: "text-xs" })}
      rowKey="id"
      pagination={members.length > 20 ? { pageSize: 20, showSizeChanger: false } : false}
      dataSource={members}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无空间成员" /> }}
      columns={[
        {
          title: "用户名",
          key: "username",
          render: (_, m) => (
            <span className="inline-flex items-baseline gap-1">
              <span className="text-ink">{m.username}</span>
              {user?.id && m.user_id === user.id && (
                <span className="text-xs text-muted">（当前用户）</span>
              )}
              {!m.last_login_at && <span className="text-xs text-muted">（尚未登录）</span>}
            </span>
          ),
        },
        {
          title: "角色",
          key: "role",
          width: 160,
          render: (_, m) => (
            <Select
              size="small"
              aria-label={`${m.username} 角色`}
              className="w-28"
              value={m.role}
              disabled={rowLocked}
              onChange={(val) => void handleMemberRoleChange(m.id, val)}
              options={ROLE_OPTIONS}
            />
          ),
        },
        {
          title: "操作",
          key: "action",
          width: 96,
          align: "right",
          render: (_, m) => (
            <Popconfirm
              title={`移除成员 ${m.username}？`}
              okText="移除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => void handleRemoveMember(m.id)}
            >
              <Button
                size="small"
                danger
                loading={deletingId === m.id}
                disabled={memberBusy || (deletingId !== null && deletingId !== m.id)}
                aria-label={`移除 ${m.username}`}
              >
                移除
              </Button>
            </Popconfirm>
          ),
        },
      ]}
    />
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="空间设置" />
      <PageBody>
        <Panel>
          <PanelToolbar>
            <SectionTitle title="空间信息" />
          </PanelToolbar>
          <div className="@container p-4">
            <Form<InfoValues>
              form={form}
              layout="vertical"
              requiredMark={false}
              initialValues={{ name: workspace.name, description: workspace.description }}
              onValuesChange={() => {
                setInfoDirty(true);
                setInfoSaved(false);
              }}
              onFinish={(values) => void saveInfo(values)}
            >
              <FormRow>
                <Form.Item
                  name="name"
                  label="空间名称"
                  rules={[{ required: true, whitespace: true, message: "请填写空间名称" }]}
                >
                  <Input aria-label="空间名称" maxLength={120} />
                </Form.Item>
                <Form.Item label="空间标识">
                  <div className="flex h-8 items-center gap-2">
                    <Text className="font-mono" aria-label="空间标识">
                      {workspace.slug}
                    </Text>
                    <Button size="small" onClick={() => void copySlug()}>
                      复制
                    </Button>
                  </div>
                </Form.Item>
              </FormRow>
              <Form.Item name="description" label="说明">
                <Input.TextArea
                  aria-label="说明"
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  maxLength={1200}
                />
              </Form.Item>
              <div className="flex items-center gap-2">
                <Button type="primary" htmlType="submit" disabled={!infoDirty} loading={savingInfo}>
                  保存空间信息
                </Button>
                {infoDirty && <Button onClick={resetInfo}>重置</Button>}
                {infoSaved && (
                  <span role="status">
                    <StatusMark state="mapped" label="已保存" />
                  </span>
                )}
              </div>
            </Form>
          </div>
          <div className="flex items-center justify-between gap-4 border-t border-rule px-4 py-3">
            <div className="flex min-w-0 flex-col gap-1">
              <h3 className="m-0 text-sm font-semibold text-ink">空间公开</h3>
              <Text type="secondary" className="text-xs">
                {workspace.is_public
                  ? "已公开：平台全部登录用户可阅读本空间内容，但不能修改。"
                  : "私有：仅空间成员和平台超级管理员可访问。"}
              </Text>
            </div>
            <Switch
              aria-label="对平台全部登录用户公开"
              checked={Boolean(workspace.is_public)}
              loading={publicBusy}
              onChange={handleSwitchChange}
            />
          </div>
        </Panel>
        <Panel
          footer={
            workspace.is_public
              ? "空间已公开：所有登录用户可阅读全部内容；成员按可查看 / 可编辑 / 管理员赋权，平台超级管理员可管理全部空间。"
              : "空间为私有：仅以下成员和平台超级管理员可访问，成员按可查看 / 可编辑 / 管理员赋权。"
          }
        >
          <PanelToolbar
            extra={
              <Button
                type="primary"
                icon={<Plus size={14} />}
                disabled={addOpen || loadingMembers || Boolean(membersLoadError)}
                onClick={() => setAddOpen(true)}
              >
                添加成员
              </Button>
            }
          >
            <SectionTitle
              title="空间成员"
              note={loadingMembers || membersLoadError ? undefined : `${members.length} 人`}
            />
          </PanelToolbar>
          {addOpen && (
            <div className="flex flex-col gap-2 border-b border-rule bg-surface-raised px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <AutoComplete
                  className="w-80"
                  value={searchText}
                  options={autoOptions}
                  allowClear
                  autoFocus
                  notFoundContent={
                    searchError ? (
                      <div className="px-2 py-1.5 text-xs text-danger">{searchError}</div>
                    ) : searchText.trim() ? (
                      <div className="px-2 py-1.5 text-xs text-muted">{USER_NOT_FOUND_TEXT}</div>
                    ) : null
                  }
                  onOpenChange={setSuggestionsOpen}
                  onFocus={() => void runUserSearch(searchText)}
                  onSearch={(val) => {
                    setSearchText(val);
                    setSelectedUserId(null);
                    setAddError("");
                    void runUserSearch(val);
                  }}
                  onChange={(val) => {
                    setSearchText(val ?? "");
                    if (!val) setSelectedUserId(null);
                  }}
                  onSelect={(val, opt) => {
                    setSearchText(val);
                    setSelectedUserId(opt.user ? opt.user.id : null);
                    setAddError("");
                  }}
                >
                  <Input
                    aria-label="搜索已有用户"
                    placeholder="按用户名搜索已有用户"
                    prefix={<Search size={14} className="text-muted" />}
                    onPressEnter={(e) => {
                      if (suggestionsOpen && autoOptions.some((o) => !o.disabled)) return;
                      e.preventDefault();
                      void handleAddMember();
                    }}
                  />
                </AutoComplete>
                <Select
                  aria-label="成员角色"
                  className="w-28"
                  value={addRole}
                  disabled={addBusy}
                  onChange={(val) => setAddRole(val)}
                  options={ROLE_OPTIONS}
                />
                <Button type="primary" loading={addBusy} onClick={() => void handleAddMember()}>
                  添加
                </Button>
                <Button disabled={addBusy} onClick={closeAddBar}>
                  取消
                </Button>
              </div>
              {addError && <Alert type="error" showIcon message={addError} />}
            </div>
          )}
          {membersContent}
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
          void updatePublic(true).then((ok) => {
            if (ok) setPublicConfirmOpen(false);
          });
        }}
      >
        <p className="m-0 text-sm leading-base text-ink-2">
          开启公开后，所有登录用户都能在工作空间目录中看到本空间，并可阅读本空间的映射、材料、会话和实例数据（包含业务库实例查询），但不能修改任何内容。
        </p>
      </Modal>
    </div>
  );
}
