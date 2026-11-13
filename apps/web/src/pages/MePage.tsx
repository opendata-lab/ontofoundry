import { Button, Descriptions, Empty, Table, Tag, Typography } from "antd";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { MeWorkspace, User } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { PlatformFrame } from "../components/PlatformFrame";
import { PageBody, PageTabs, Panel, PanelToolbar, SectionTitle } from "../components/layout";
import { ROLE_LABELS } from "../hooks/useWorkspacePermissions";

const { Text } = Typography;

/** Read-only personal profile and workspace memberships (/me). */
export function MePage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<MeWorkspace[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    Promise.all([api.me(), api.meWorkspaces()])
      .then(([u, ws]) => {
        setUser(u);
        setWorkspaces(ws.items);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!user) return <LoadingSurface label="正在读取个人中心…" />;

  return (
    <PlatformFrame user={user}>
      <PageTabs
        title="个人中心"
        note="仅限只读查看本人账号与空间成员身份。"
        actions={
          <Button icon={<ArrowLeft size={14} />} onClick={() => navigate("/")}>
            返回工作空间
          </Button>
        }
        activeKey="profile"
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
            disabled: true,
            label: (
              <span className="inline-flex items-center gap-2">
                <span>个人令牌</span>
                <Tag className="m-0 border-0 bg-surface-soft text-muted">
                  随外部智能体网关上线
                </Tag>
              </span>
            ),
            children: null,
          },
        ]}
      />
    </PlatformFrame>
  );
}
