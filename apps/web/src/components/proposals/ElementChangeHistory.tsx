import { Alert, Button, Spin, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { proposalsApi } from "../../api/client";
import type {
  ChangeActorKind,
  ChangeAction,
  ChangeEvent,
  ChangeSubject,
  FieldChange,
  Json,
} from "../../api/types";
import { FieldDiff } from "./FieldDiff";

const { Text } = Typography;

const ACTOR_LABEL: Record<ChangeActorKind, string> = {
  human: "人工",
  agent: "智能体",
  import: "导入",
};

const SUBJECT_LABEL: Record<ChangeSubject, string> = {
  proposal: "提案",
  draft: "草稿",
  version: "版本",
};

const ACTION_LABEL: Record<ChangeAction, string> = {
  created: "生成提案",
  revised: "修订提案",
  superseded: "被新提案取代",
  accepted: "接受提案",
  rejected: "拒绝提案",
  restored: "恢复提案",
  back_to_pending: "退回待审",
  added: "草稿新增",
  updated: "草稿修改",
  removed: "草稿移除",
  published: "发布版本",
};

const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  pending: "待审",
  accepted: "已接受",
  rejected: "已拒绝",
  superseded: "已取代",
};

function asRecord(value: unknown): Record<string, Json> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, Json>;
}

function isEmptyValue(value: unknown): boolean {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0)
  );
}

function diffObjects(
  beforeObj: Record<string, Json> | null,
  afterObj: Record<string, Json> | null,
): FieldChange[] {
  if (!beforeObj && !afterObj) return [];
  const keys = Array.from(
    new Set([
      ...(beforeObj ? Object.keys(beforeObj) : []),
      ...(afterObj ? Object.keys(afterObj) : []),
    ]),
  ).filter((key) => key !== "id");

  const changes: FieldChange[] = [];
  for (const key of keys) {
    const beforeVal = beforeObj?.[key] ?? null;
    const afterVal = afterObj?.[key] ?? null;
    if (!beforeObj) {
      if (!isEmptyValue(afterVal)) {
        changes.push({ path: key, before: null, after: afterVal });
      }
      continue;
    }
    if (!afterObj) {
      if (!isEmptyValue(beforeVal)) {
        changes.push({ path: key, before: beforeVal, after: null });
      }
      continue;
    }
    if (JSON.stringify(beforeVal) !== JSON.stringify(afterVal)) {
      changes.push({ path: key, before: beforeVal, after: afterVal });
    }
  }
  return changes;
}

function eventFieldDiffs(event: ChangeEvent): FieldChange[] {
  if (event.subject === "draft") {
    return diffObjects(asRecord(event.before), asRecord(event.after));
  }
  if (event.subject === "proposal") {
    const beforeSnap = asRecord(event.before);
    const afterSnap = asRecord(event.after);
    if (event.action === "created") {
      return diffObjects(asRecord(afterSnap?.before), asRecord(afterSnap?.after));
    }
    if (event.action === "revised") {
      const contentDiff = diffObjects(asRecord(beforeSnap?.after), asRecord(afterSnap?.after));
      if (contentDiff.length > 0) return contentDiff;
      return diffObjects(asRecord(afterSnap?.before), asRecord(afterSnap?.after));
    }
  }
  return [];
}

function statusTransition(event: ChangeEvent): string | null {
  if (event.subject !== "proposal") return null;
  const beforeStatus = asRecord(event.before)?.status;
  const afterStatus = asRecord(event.after)?.status;
  if (typeof afterStatus !== "string") return null;
  const afterLabel = PROPOSAL_STATUS_LABEL[afterStatus] ?? afterStatus;
  if (typeof beforeStatus === "string" && beforeStatus !== afterStatus) {
    const beforeLabel = PROPOSAL_STATUS_LABEL[beforeStatus] ?? beforeStatus;
    return `${beforeLabel} → ${afterLabel}`;
  }
  if (event.action === "created") return afterLabel;
  return null;
}

export function ElementChangeHistory({
  workspaceId,
  sessionId,
  targetId,
  refreshKey,
  names,
}: {
  workspaceId: string;
  sessionId: string;
  targetId: string;
  refreshKey?: number | string;
  names?: Map<string, string>;
}) {
  const [items, setItems] = useState<ChangeEvent[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const generationRef = useRef(0);

  useEffect(() => {
    const generation = ++generationRef.current;
    setLoading(true);
    setLoadingMore(false);
    setError("");
    proposalsApi
      .changeEvents(workspaceId, sessionId, { target_id: targetId, limit: 20 })
      .then((page) => {
        if (generationRef.current !== generation) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch((err: unknown) => {
        if (generationRef.current !== generation) return;
        setItems([]);
        setNextCursor(null);
        setError(err instanceof Error ? err.message : "修改记录加载失败");
      })
      .finally(() => {
        if (generationRef.current === generation) {
          setLoading(false);
        }
      });
    return () => {
      generationRef.current += 1;
    };
  }, [workspaceId, sessionId, targetId, refreshKey]);

  const loadMore = async () => {
    if (!nextCursor || loading || loadingMore) return;
    const generation = generationRef.current;
    setLoadingMore(true);
    setError("");
    try {
      const page = await proposalsApi.changeEvents(workspaceId, sessionId, {
        target_id: targetId,
        limit: 20,
        cursor: nextCursor,
      });
      if (generationRef.current !== generation) return;
      setItems((prev) => [...prev, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      if (generationRef.current !== generation) return;
      setError(err instanceof Error ? err.message : "加载更多记录失败");
    } finally {
      if (generationRef.current === generation) {
        setLoadingMore(false);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2" role="status" aria-label="正在加载修改记录">
        <Spin size="small" />
        <Text type="secondary" className="text-xs">
          正在加载修改记录…
        </Text>
      </div>
    );
  }

  if (error && !items.length) {
    return <Alert type="error" showIcon message={error} />;
  }

  if (!items.length) {
    return <Text type="secondary">暂无修改记录</Text>;
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="m-0 flex list-none flex-col gap-3 p-0" aria-label="元素修改记录">
        {items.map((event) => {
          const diffs = eventFieldDiffs(event);
          const transition = statusTransition(event);
          const who = event.actor_display_name
            ? `${ACTOR_LABEL[event.actor_kind]} · ${event.actor_display_name}`
            : ACTOR_LABEL[event.actor_kind];
          return (
            <li
              key={event.id}
              className="flex flex-col gap-2 border-b border-rule-soft pb-3 last:border-b-0 last:pb-0"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Tag className="m-0">{who}</Tag>
                  <Tag className="m-0">{SUBJECT_LABEL[event.subject]}</Tag>
                  <span className="font-medium text-ink">
                    {ACTION_LABEL[event.action]}
                  </span>
                  {transition && (
                    <Text type="secondary" className="text-xs">
                      {transition}
                    </Text>
                  )}
                </div>
                <Text type="secondary" className="text-xs">
                  {new Date(event.at).toLocaleString("zh-CN", { hour12: false })}
                </Text>
              </div>
              {diffs.length > 0 && (
                <FieldDiff
                  changes={diffs}
                  beforeLabel="修改前"
                  afterLabel="修改后"
                  names={names}
                />
              )}
            </li>
          );
        })}
      </ul>
      {error && <Alert type="error" showIcon message={error} />}
      {nextCursor && (
        <div>
          <Button size="small" loading={loadingMore} onClick={() => void loadMore()}>
            加载更多
          </Button>
        </div>
      )}
    </div>
  );
}
