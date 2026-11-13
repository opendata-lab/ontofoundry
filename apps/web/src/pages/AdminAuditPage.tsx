import {
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Select,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, adminApi, api } from "../api/client";
import type {
  AdminUser,
  AdminWorkspace,
  GatewayCallDetail,
  GatewayCallSummary,
  GatewayCallWorkspace,
  GatewayOutcome,
  Json,
  User,
} from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { NoAccessResult } from "../components/NoAccessResult";
import { PageHeader } from "../components/PageHeader";
import { PlatformFrame } from "../components/PlatformFrame";
import {
  PageBody,
  PageToolbar,
  Panel,
  SectionTitle,
  StatusMark,
} from "../components/layout";

const { Text } = Typography;
const { RangePicker } = DatePicker;
const PAGE_SIZE = 20;

const TOOL_OPTIONS = [
  { value: "list_spaces", label: "list_spaces" },
  { value: "search_ontology", label: "search_ontology" },
  { value: "get_ontology", label: "get_ontology" },
  { value: "submit_feedback", label: "submit_feedback" },
];

const OUTCOME_OPTIONS: { value: GatewayOutcome; label: string }[] = [
  { value: "ok", label: "成功" },
  { value: "error", label: "失败" },
  { value: "started", label: "未完成" },
];

function formatAuditTime(iso: string) {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

function formatJson(value: Json) {
  return JSON.stringify(value, null, 2);
}

function formatWorkspaceTag(ws: GatewayCallWorkspace) {
  const base = ws.name || ws.id;
  if (ws.name && ws.version_number !== null && ws.version_number !== undefined) {
    return `${base} · v${ws.version_number}`;
  }
  return base;
}

function renderOutcome(outcome: GatewayOutcome, errorCode: string | null) {
  if (outcome === "ok") return <StatusMark state="mapped" label="成功" />;
  if (outcome === "error") {
    return (
      <StatusMark
        state="error"
        label={errorCode ? `失败 (${errorCode})` : "失败"}
      />
    );
  }
  return <StatusMark state="pending" label="未完成" />;
}

/** Platform admin external-agent gateway audit log (/admin/audit). */
export function AdminAuditPage() {
  const navigate = useNavigate();

  const [me, setMe] = useState<User | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [pageError, setPageError] = useState("");

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [workspaces, setWorkspaces] = useState<AdminWorkspace[]>([]);

  const [userId, setUserId] = useState<string | undefined>(undefined);
  const [workspaceId, setWorkspaceId] = useState<string | undefined>(undefined);
  const [tool, setTool] = useState<string | undefined>(undefined);
  const [outcome, setOutcome] = useState<GatewayOutcome | undefined>(undefined);
  const [timeRange, setTimeRange] = useState<[Dayjs | null, Dayjs | null] | null>(
    null,
  );

  const [page, setPage] = useState(1);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [calls, setCalls] = useState<GatewayCallSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const listSeq = useRef(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GatewayCallDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const detailSeq = useRef(0);

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
    let live = true;
    void Promise.allSettled([adminApi.users(), adminApi.workspaces()]).then(
      ([uRes, wRes]) => {
        if (!live) return;
        if (uRes.status === "fulfilled") setUsers(uRes.value.items);
        if (wRes.status === "fulfilled") setWorkspaces(wRes.value.items);
      },
    );
    return () => {
      live = false;
    };
  }, [me?.is_platform_admin, forbidden]);

  const fromIso = timeRange?.[0]?.toISOString();
  const toIso = timeRange?.[1]?.toISOString();
  const currentCursor = cursors[page - 1];

  useEffect(() => {
    if (!me?.is_platform_admin || forbidden) return;
    const seq = ++listSeq.current;
    setLoadingList(true);
    setListError("");
    adminApi
      .gatewayCalls({
        user_id: userId,
        workspace_id: workspaceId,
        tool,
        outcome,
        from: fromIso,
        to: toIso,
        cursor: currentCursor,
        limit: PAGE_SIZE,
      })
      .then((res) => {
        if (seq !== listSeq.current) return;
        setCalls(res.items);
        setNextCursor(res.next_cursor);
      })
      .catch((e: unknown) => {
        if (seq !== listSeq.current) return;
        if (e instanceof ApiError && e.status === 403) {
          setForbidden(true);
          return;
        }
        setListError(e instanceof Error ? e.message : "加载调用记录失败");
      })
      .finally(() => {
        if (seq === listSeq.current) setLoadingList(false);
      });
  }, [
    me?.is_platform_admin,
    forbidden,
    userId,
    workspaceId,
    tool,
    outcome,
    fromIso,
    toIso,
    currentCursor,
    refreshTick,
  ]);

  const userOptions = useMemo(
    () =>
      users.map((u) => ({
        value: u.id,
        label: `${u.display_name} (${u.username})`,
      })),
    [users],
  );

  const workspaceOptions = useMemo(
    () =>
      workspaces.map((w) => ({
        value: w.id,
        label: w.name,
      })),
    [workspaces],
  );

  if (pageError) return <ErrorSurface message={pageError} retry={loadMe} />;
  if (!me) return <LoadingSurface label="正在检查访问权限…" />;

  if (forbidden || !me.is_platform_admin) {
    return (
      <PlatformFrame user={me}>
        <NoAccessResult subtitle="只有平台管理员（ADMIN_USERS）可以访问用户审计。" />
      </PlatformFrame>
    );
  }

  const resetPaging = () => {
    setPage(1);
    setCursors([undefined]);
  };

  const hasFilters = Boolean(
    userId || workspaceId || tool || outcome || fromIso || toIso,
  );

  const clearFilters = () => {
    setUserId(undefined);
    setWorkspaceId(undefined);
    setTool(undefined);
    setOutcome(undefined);
    setTimeRange(null);
    resetPaging();
  };

  const openDetail = async (callId: string) => {
    const seq = ++detailSeq.current;
    setSelectedId(callId);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const result = await adminApi.gatewayCall(callId);
      if (seq === detailSeq.current) setDetail(result);
    } catch (e) {
      if (seq === detailSeq.current) {
        if (e instanceof ApiError && e.status === 403) {
          setSelectedId(null);
          setForbidden(true);
          return;
        }
        setDetailError(e instanceof Error ? e.message : "加载调用详情失败");
      }
    } finally {
      if (seq === detailSeq.current) setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    detailSeq.current++;
    setSelectedId(null);
    setDetail(null);
    setDetailError("");
  };

  const columns: ColumnsType<GatewayCallSummary> = [
    {
      title: "时间",
      key: "created_at",
      width: 170,
      render: (_, call) => (
        <span className="tabular-nums text-xs whitespace-nowrap">
          {formatAuditTime(call.created_at)}
        </span>
      ),
    },
    {
      title: "用户",
      key: "user",
      width: 120,
      render: (_, call) => call.user.display_name || call.user.id,
    },
    {
      title: "工具",
      key: "tool",
      width: 150,
      render: (_, call) => <code className="text-xs">{call.tool}</code>,
    },
    {
      title: "涉及空间",
      key: "workspaces",
      render: (_, call) =>
        call.workspaces.length ? (
          <span className="flex flex-wrap gap-1">
            {call.workspaces.map((ws) => (
              <Tag
                key={ws.id}
                className="m-0"
                title={ws.name ? ws.id : undefined}
              >
                {formatWorkspaceTag(ws)}
              </Tag>
            ))}
          </span>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "请求摘要",
      key: "summary",
      render: (_, call) => (
        <span className="text-sm text-ink-2">{call.summary || "—"}</span>
      ),
    },
    {
      title: "结果",
      key: "outcome",
      width: 180,
      render: (_, call) => renderOutcome(call.outcome, call.error_code),
    },
    {
      title: "耗时",
      key: "duration_ms",
      width: 96,
      align: "right",
      render: (_, call) =>
        call.duration_ms !== null && call.duration_ms !== undefined ? (
          <span className="tabular-nums text-xs whitespace-nowrap">
            {call.duration_ms} ms
          </span>
        ) : (
          <Text type="secondary" className="text-xs">
            —
          </Text>
        ),
    },
  ];

  return (
    <PlatformFrame user={me}>
      <PageHeader
        title="用户审计"
        note="查看外部智能体经用户网关发起的跨空间 MCP 调用记录，按开始时间倒序排列（异步写入，调用后数秒内出现）。"
      >
        <Button
          icon={<RefreshCw className="size-icon-sm" />}
          loading={loadingList}
          onClick={() => setRefreshTick((n) => n + 1)}
        >
          刷新
        </Button>
        <Button icon={<ArrowLeft size={14} />} onClick={() => navigate("/")}>
          返回工作空间
        </Button>
      </PageHeader>
      <PageBody>
        <PageToolbar
          extra={
            hasFilters ? (
              <Button size="small" onClick={clearFilters}>
                重置筛选
              </Button>
            ) : null
          }
        >
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            aria-label="筛选用户"
            placeholder="全部用户"
            className="w-44"
            value={userId}
            options={userOptions}
            onChange={(val) => {
              setUserId(val);
              resetPaging();
            }}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            aria-label="筛选空间"
            placeholder="全部空间"
            className="w-44"
            value={workspaceId}
            options={workspaceOptions}
            onChange={(val) => {
              setWorkspaceId(val);
              resetPaging();
            }}
          />
          <Select
            allowClear
            aria-label="筛选工具"
            placeholder="全部工具"
            className="w-40"
            value={tool}
            options={TOOL_OPTIONS}
            onChange={(val) => {
              setTool(val);
              resetPaging();
            }}
          />
          <Select
            allowClear
            aria-label="筛选结果"
            placeholder="全部结果"
            className="w-32"
            value={outcome}
            options={OUTCOME_OPTIONS}
            onChange={(val) => {
              setOutcome(val);
              resetPaging();
            }}
          />
          <RangePicker
            showTime
            allowClear
            placeholder={["开始时间", "结束时间"]}
            value={timeRange}
            onChange={(vals) => {
              setTimeRange(vals);
              resetPaging();
            }}
          />
        </PageToolbar>

        {listError && (
          <Alert
            type="error"
            showIcon
            message={listError}
            action={
              <Button size="small" onClick={() => setRefreshTick((n) => n + 1)}>
                重试
              </Button>
            }
          />
        )}

        <Panel>
          <Table<GatewayCallSummary>
            size="middle"
            rowKey="id"
            loading={loadingList}
            dataSource={calls}
            columns={columns}
            pagination={false}
            onHeaderRow={() => ({ className: "text-xs whitespace-nowrap" })}
            onRow={(record) => ({
              onClick: () => void openDetail(record.id),
              className: "cursor-pointer",
            })}
            locale={{
              emptyText: (
                <Empty
                  description={
                    hasFilters ? "没有符合筛选条件的调用记录" : "暂无网关调用记录"
                  }
                />
              ),
            }}
          />
          {(page > 1 || nextCursor) && (
            <div className="flex items-center justify-end gap-2 border-t border-rule px-4 py-2">
              <Text type="secondary" className="text-xs">
                每页 {PAGE_SIZE} 条
              </Text>
              <Button
                size="small"
                disabled={page <= 1 || loadingList}
                onClick={() => setPage((p) => p - 1)}
              >
                上一页
              </Button>
              <span className="tabular-nums text-xs">第 {page} 页</span>
              <Button
                size="small"
                disabled={!nextCursor || loadingList}
                onClick={() => {
                  if (!nextCursor) return;
                  setCursors((prev) => {
                    const next = prev.slice(0, page);
                    next[page] = nextCursor;
                    return next;
                  });
                  setPage((p) => p + 1);
                }}
              >
                下一页
              </Button>
            </div>
          )}
        </Panel>
      </PageBody>

      <Drawer
        open={Boolean(selectedId)}
        title={detail ? `调用详情 · ${detail.tool}` : "调用详情"}
        width={680}
        onClose={closeDetail}
      >
        {detailLoading ? (
          <div className="flex justify-center py-8">
            <Spin />
          </div>
        ) : detailError ? (
          <Alert type="error" showIcon message={detailError} />
        ) : detail ? (
          <div className="flex flex-col gap-4">
            <Descriptions column={2} size="small" colon={false}>
              <Descriptions.Item label="调用时间">
                <span className="tabular-nums text-xs">
                  {formatAuditTime(detail.created_at)}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="用户">
                {detail.user.display_name || detail.user.id}
              </Descriptions.Item>
              <Descriptions.Item label="工具">
                <code>{detail.tool}</code>
              </Descriptions.Item>
              <Descriptions.Item label="结果">
                {renderOutcome(detail.outcome, detail.error_code)}
              </Descriptions.Item>
              <Descriptions.Item label="耗时">
                {detail.duration_ms !== null && detail.duration_ms !== undefined
                  ? `${detail.duration_ms} ms`
                  : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="请求 ID">
                <code className="text-xs">{detail.request_id}</code>
              </Descriptions.Item>
              <Descriptions.Item label="涉及空间" span={2}>
                {detail.workspaces.length ? (
                  <span className="flex flex-wrap gap-1">
                    {detail.workspaces.map((ws) => (
                      <Tag
                        key={ws.id}
                        className="m-0"
                        title={ws.version_id ? `版本 ID: ${ws.version_id}` : ws.id}
                      >
                        {formatWorkspaceTag(ws)}
                      </Tag>
                    ))}
                  </span>
                ) : (
                  <Text type="secondary">—</Text>
                )}
              </Descriptions.Item>
            </Descriptions>

            {(detail.outcome === "error" ||
              detail.error_code ||
              detail.error_message) && (
              <Alert
                type="error"
                showIcon
                message={
                  detail.error_code
                    ? `错误码：${detail.error_code}`
                    : "调用失败"
                }
                description={detail.error_message || undefined}
              />
            )}

            <div className="flex flex-col gap-2">
              <SectionTitle title="完整请求（arguments）" />
              <pre className="m-0 max-h-review-code overflow-auto rounded-xs border border-rule bg-surface-raised p-3 font-mono text-xs leading-base text-ink">
                {formatJson(detail.arguments)}
              </pre>
            </div>

            <div className="flex flex-col gap-2">
              <SectionTitle title="完整返回（response）" />
              {detail.response === null || detail.response === undefined ? (
                <Text type="secondary" className="text-xs">
                  {detail.outcome === "started"
                    ? "调用尚未完成，暂无返回内容"
                    : "无返回内容"}
                </Text>
              ) : (
                <pre className="m-0 max-h-review-code overflow-auto rounded-xs border border-rule bg-surface-raised p-3 font-mono text-xs leading-base text-ink">
                  {formatJson(detail.response)}
                </pre>
              )}
            </div>
          </div>
        ) : null}
      </Drawer>
    </PlatformFrame>
  );
}
