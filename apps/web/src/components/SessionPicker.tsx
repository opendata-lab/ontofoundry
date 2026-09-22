import { ChevronDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ModelingSession,
  ModelingSessionSummary,
} from "../api/types";

const ACTIVE_STATUSES = new Set([
  "submitting",
  "queued",
  "running",
  "waiting_input",
  "waiting_permission",
]);

const STATUS_LABELS: Record<string, string> = {
  idle: "未开始",
  submitting: "提交中",
  queued: "排队中",
  running: "运行中",
  waiting_input: "等待输入",
  waiting_permission: "等待确认",
  finished: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

function timestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
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
  const root = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    search.current?.focus();
    return () => {
      document.removeEventListener("mousedown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const visible = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return [...sessions]
      .filter((item) =>
        item.title.toLocaleLowerCase("zh-CN").includes(normalized),
      )
      .sort((left, right) => {
        const activity =
          Number(ACTIVE_STATUSES.has(right.task_status)) -
          Number(ACTIVE_STATUSES.has(left.task_status));
        return (
          activity ||
          new Date(right.updated_at).getTime() -
            new Date(left.updated_at).getTime()
        );
      });
  }, [query, sessions]);

  return (
    <div className="session-picker" ref={root}>
      <button
        type="button"
        className="session-picker-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          {session?.title ??
            (sessionId ? "正在加载会话…" : "选择建模会话")}
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          className="session-picker-popover"
          role="dialog"
          aria-label="选择建模会话"
        >
          <label className="session-picker-search">
            <Search size={14} aria-hidden="true" />
            <input
              ref={search}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索会话标题"
              aria-label="搜索建模会话"
            />
          </label>
          <div className="session-picker-table-wrap">
            <table className="session-picker-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>状态</th>
                  <th>最近更新时间</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr
                    key={item.id}
                    className={item.id === sessionId ? "is-selected" : ""}
                    aria-selected={item.id === sessionId}
                    tabIndex={0}
                    onClick={() => {
                      onSelect(item.id);
                      setOpen(false);
                      setQuery("");
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(item.id);
                        setOpen(false);
                        setQuery("");
                      }
                    }}
                  >
                    <td title={item.title}>{item.title}</td>
                    <td>
                      <span
                        className={`session-status session-status--${item.task_status}`}
                      >
                        {statusLabel(item.task_status)}
                      </span>
                    </td>
                    <td>{timestamp(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visible.length && (
              <p className="session-picker-empty">
                {sessions.length ? "没有匹配的会话" : "暂无建模会话"}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
