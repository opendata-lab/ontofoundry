import { Alert, Button, Card, Form, Input, Select, Space, Spin, Table, Tag, Typography } from "antd";
import { PageBody, PageHeader } from "../components/PageHeader";
import { useCallback, useEffect, useState } from "react";
import { workspaceRequest } from "../api/client";
import type { DataAgentHealth, Member } from "../api/types";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

const { Text } = Typography;

export function SettingsPage() {
  const { workspace, user, refresh } = useWorkspaceContext();
  const admin = workspace.role === "admin";
  const [members, setMembers] = useState<Member[]>([]);
  const [dataagentHealth, setDataagentHealth] = useState<DataAgentHealth | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [infoDirty, setInfoDirty] = useState(false);
  const [memberDirty, setMemberDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [memberForm] = Form.useForm<{ subject: string; role: Member["role"] }>();
  usePageTab({ dirty: infoDirty || memberDirty, busy });
  const load = useCallback(
    () => workspaceRequest<{ items: Member[] }>(workspace.id, "/members").then((r) => setMembers(r.items)),
    [workspace.id],
  );
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    workspaceRequest<DataAgentHealth>(workspace.id, "/settings/dataagent-health")
      .then(setDataagentHealth)
      .catch((e: Error) => setError(e.message));
  }, [workspace.id, load]);
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
      <Card title="空间信息" size="small" className="max-w-[880px]">
        <Form
          layout="vertical"
          disabled={!admin}
          initialValues={{ name: workspace.name, description: workspace.description }}
          onValuesChange={() => setInfoDirty(true)}
          onFinish={(values: { name: string; description: string }) => {
            setBusy(true);
            workspaceRequest(workspace.id, "", values, "PATCH")
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
          {admin && (
            <Space>
              <Button type="primary" htmlType="submit" loading={busy}>
                保存空间信息
              </Button>
              {notice && <Text type="success">{notice}</Text>}
            </Space>
          )}
        </Form>
      </Card>
      <Card title="空间成员" size="small" className="max-w-[880px]">
        <Text type="secondary" className="mb-3 block">
          非成员可查看已发布本体；材料、草稿、映射和实例仅成员可见。
        </Text>
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={members}
          columns={[
            { title: "用户", dataIndex: "name" },
            { title: "身份标识", dataIndex: "subject" },
            { title: "角色", key: "role", render: (_, m) => (m.role === "admin" ? "管理员" : "成员") },
            {
              title: "",
              key: "action",
              width: 80,
              render: (_, m) =>
                admin && m.user_id !== user.id ? (
                  <Button
                    size="small"
                    type="link"
                    danger
                    onClick={() =>
                      workspaceRequest(workspace.id, "/members/" + m.id, undefined, "DELETE")
                        .then(load)
                        .catch((e: Error) => setError(e.message))
                    }
                  >
                    移除
                  </Button>
                ) : null,
            },
          ]}
        />
        {admin && (
          <Form
            form={memberForm}
            layout="inline"
            className="!mt-3"
            initialValues={{ role: "member" }}
            onValuesChange={() => setMemberDirty(true)}
            onFinish={(values) => {
              setBusy(true);
              workspaceRequest(workspace.id, "/members", values)
                .then(() => {
                  setMemberDirty(false);
                  memberForm.resetFields();
                  return load();
                })
                .catch((e: Error) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            <Form.Item name="subject" rules={[{ required: true, message: "请填写身份标识" }]}>
              <Input aria-label="成员身份标识" placeholder="provider:sub，需先登录过平台" className="!w-[300px]" />
            </Form.Item>
            <Form.Item name="role">
              <Select
                aria-label="成员角色"
                className="!w-[120px]"
                options={[
                  { value: "member", label: "成员" },
                  { value: "admin", label: "管理员" },
                ]}
              />
            </Form.Item>
            <Button htmlType="submit" loading={busy}>
              添加成员
            </Button>
          </Form>
        )}
      </Card>
      <Card title="DataAgent 连通性" size="small" className="max-w-[880px]">
        <Text type="secondary" className="mb-3 block">
          配置检查。地址、站点与凭据均由部署环境和 DataAgent 管理端配置。
        </Text>
        {dataagentHealth ? (
          <Table
            size="small"
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
                  <Tag color={check.ok ? "success" : "error"} className="!m-0">
                    {check.ok ? "通过" : "需处理"}
                  </Tag>
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
          <Spin />
        )}
      </Card>
      </PageBody>
    </div>
  );
}
