import { App, Button, Empty, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { FeedbackItem } from "../api/types";
import { ErrorSurface } from "../components/AsyncState";
import { NoAccessResult } from "../components/NoAccessResult";
import { PageBody, PageHeader, Panel } from "../components/layout";
import { usePageActive, usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useWorkspacePermissions } from "../hooks/useWorkspacePermissions";

const { Text } = Typography;
const PAGE_SIZE = 20;

function formatFeedbackTime(iso: string) {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}

/** Read-only workspace feedback log submitted by external agents (/workspaces/:id/feedback). */
export function FeedbackPage() {
  const { workspace } = useWorkspaceContext();
  const { canManage } = useWorkspacePermissions();
  const active = usePageActive();
  const { message } = App.useApp();

  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState("");
  const requestSeq = useRef(0);

  usePageTab({ title: "用户反馈" });

  const loadInitial = useCallback(async () => {
    if (!canManage) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    setError("");
    setForbidden(false);
    try {
      const page = await api.feedback(workspace.id, { limit: PAGE_SIZE });
      if (seq !== requestSeq.current) return;
      setItems(page.items);
      setNextCursor(page.next_cursor);
    } catch (e) {
      if (seq !== requestSeq.current) return;
      if (e instanceof ApiError && e.status === 403) {
        setForbidden(true);
        return;
      }
      setError(e instanceof Error ? e.message : "加载用户反馈失败");
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [workspace.id, canManage]);

  useEffect(() => {
    if (!active || !canManage) return;
    void loadInitial();
  }, [active, canManage, loadInitial]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return;
    const seq = ++requestSeq.current;
    setLoadingMore(true);
    try {
      const page = await api.feedback(workspace.id, {
        cursor: nextCursor,
        limit: PAGE_SIZE,
      });
      if (seq !== requestSeq.current) return;
      setItems((prev) => [...prev, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (e) {
      if (seq !== requestSeq.current) return;
      if (e instanceof ApiError && e.status === 403) {
        setForbidden(true);
        return;
      }
      void message.error(e instanceof Error ? e.message : "加载更多反馈失败");
    } finally {
      if (seq === requestSeq.current) setLoadingMore(false);
    }
  };

  if (!canManage || forbidden) {
    return (
      <div className="flex h-full min-h-0 flex-col bg-canvas">
        <NoAccessResult subtitle="只有该工作空间的管理员或平台管理员可以查看「用户反馈」。" />
      </div>
    );
  }

  if (error) {
    return <ErrorSurface message={error} retry={() => void loadInitial()} />;
  }

  const columns: ColumnsType<FeedbackItem> = [
    {
      title: "时间",
      key: "created_at",
      width: 170,
      render: (_, item) => (
        <span className="tabular-nums text-xs whitespace-nowrap">
          {formatFeedbackTime(item.created_at)}
        </span>
      ),
    },
    {
      title: "提交者",
      key: "user",
      width: 120,
      render: (_, item) => item.user.display_name || item.user.id,
    },
    {
      title: "类型",
      key: "kind",
      width: 88,
      render: (_, item) => (
        <Tag
          className={
            item.kind === "correction"
              ? "m-0 border-0 bg-warning-soft text-warning"
              : "m-0 border-0 bg-accent-soft text-accent"
          }
        >
          {item.kind === "correction" ? "纠正" : "建议"}
        </Tag>
      ),
    },
    {
      title: "用户原话",
      key: "user_text",
      render: (_, item) => (
        <div className="whitespace-pre-wrap break-words text-sm text-ink">
          {item.user_text}
        </div>
      ),
    },
    {
      title: "智能体说明",
      key: "agent_text",
      render: (_, item) => (
        <div className="whitespace-pre-wrap break-words text-sm text-ink-2">
          {item.agent_text}
        </div>
      ),
    },
    {
      title: "相关元素",
      key: "elements",
      width: 220,
      render: (_, item) =>
        item.elements.length ? (
          <span className="flex flex-wrap gap-1">
            {item.elements.map((el) => {
              const label = el.display_name || el.name || el.id;
              return (
                <Tag
                  key={el.id}
                  className="m-0"
                  title={el.display_name || el.name ? el.id : undefined}
                >
                  {label}
                </Tag>
              );
            })}
          </span>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "版本",
      key: "version_number",
      width: 96,
      render: (_, item) =>
        item.version_number !== null && item.version_number !== undefined ? (
          <span className="tabular-nums text-xs">v{item.version_number}</span>
        ) : (
          <Text type="secondary" className="text-xs">
            未发布
          </Text>
        ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader
        title="用户反馈"
        note="外部智能体在使用过程中记录的纠错与建议，按提交时间倒序排列（只读）。"
      >
        <Button
          icon={<RefreshCw className="size-icon-sm" />}
          loading={loading}
          onClick={() => void loadInitial()}
        >
          刷新
        </Button>
      </PageHeader>
      <PageBody>
        <Panel>
          <Table<FeedbackItem>
            size="middle"
            rowKey="id"
            loading={loading}
            dataSource={items}
            columns={columns}
            pagination={false}
            onHeaderRow={() => ({ className: "text-xs whitespace-nowrap" })}
            locale={{
              emptyText: <Empty description="暂无用户反馈记录" />,
            }}
          />
          {nextCursor && (
            <div className="flex items-center justify-center border-t border-rule px-4 py-2">
              <Button loading={loadingMore} onClick={() => void loadMore()}>
                加载更多
              </Button>
            </div>
          )}
        </Panel>
      </PageBody>
    </div>
  );
}
