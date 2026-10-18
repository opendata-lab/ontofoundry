import { Button, Input, Popover, Table } from "antd";
import { StatusMark, type StatusState } from "./layout";
import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import type { ModelingSession, ModelingSessionSummary } from "../api/types";

const ACTIVE_STATUSES = new Set(["submitting", "queued", "running", "waiting_input", "waiting_permission"]);

const STATUS: Record<string, { text: string; state: StatusState }> = {
  idle: { text: "未开始", state: "unmapped" },
  submitting: { text: "提交中", state: "info" },
  queued: { text: "排队中", state: "info" },
  running: { text: "运行中", state: "info" },
  waiting_input: { text: "等待输入", state: "partial" },
  waiting_permission: { text: "等待确认", state: "partial" },
  finished: { text: "已完成", state: "mapped" },
  failed: { text: "失败", state: "error" },
  cancelled: { text: "已取消", state: "unmapped" },
};

function timestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

export function SessionPicker({
  session,
  sessionId,
  sessions,
  onSelect,
}: {
  session: ModelingSession | null;
  sessionId: string | null;
  sessions: ModelingSessionSummary[];
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return [...sessions]
      .filter((item) => item.title.toLocaleLowerCase("zh-CN").includes(normalized))
      .sort((left, right) => {
        const activity = Number(ACTIVE_STATUSES.has(right.task_status)) - Number(ACTIVE_STATUSES.has(left.task_status));
        return activity || new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
      });
  }, [query, sessions]);
  const choose = (id: string) => {
    onSelect(id);
    setOpen(false);
    setQuery("");
  };
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomLeft"
      destroyOnHidden
      content={
        <div className="flex w-review-code max-w-full flex-col gap-2" role="dialog" aria-label="选择建模会话">
          <Input.Search
            autoFocus
            allowClear
            size="small"
            aria-label="搜索建模会话"
            placeholder="搜索会话标题"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            scroll={{ y: 320 }}
            dataSource={visible}
            locale={{ emptyText: sessions.length ? "没有匹配的会话" : "暂无建模会话" }}
            rowClassName={(item) => `cursor-pointer ${item.id === sessionId ? "bg-accent-soft" : ""}`}
            onRow={(item) => ({
              tabIndex: 0,
              "aria-selected": item.id === sessionId,
              onClick: () => choose(item.id),
              onKeyDown: (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  choose(item.id);
                }
              },
            })}
            columns={[
              { title: "标题", key: "title", ellipsis: true, render: (_, item) => <span title={item.title}>{item.title}</span> },
              {
                title: "状态",
                key: "status",
                width: 96,
                render: (_, item) => (
                  <StatusMark state={STATUS[item.task_status]?.state ?? "unmapped"} label={STATUS[item.task_status]?.text ?? item.task_status} />
                ),
              },
              { title: "最近更新时间", key: "updated", width: 120, render: (_, item) => timestamp(item.updated_at) },
            ]}
          />
        </div>
      }
    >
      <Button aria-haspopup="dialog" aria-expanded={open} className="max-w-xs">
        <span className="truncate">{session?.title ?? (sessionId ? "正在加载会话…" : "选择建模会话")}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </Button>
    </Popover>
  );
}
