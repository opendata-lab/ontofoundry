import { Brain, CheckCircle2, LoaderCircle, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { modelingApi } from "../api/client";
import type { ModelingSession } from "../api/types";
import {
  createAgentStreamState,
  processDataAgentRecord,
  streamSessionEvents,
  type AgentBlock,
  type AgentStreamState,
} from "../lib/dataagentStream";
import { Markdown } from "./Markdown";

function printable(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function StreamBlock({ block }: { block: AgentBlock }) {
  if (block.type === "text") return block.content ? <Markdown>{block.content}</Markdown> : null;
  if (block.type === "thinking")
    return (
      <details className="agent-reasoning" open={block.status === "streaming"}>
        <summary><Brain size={13} />分析过程</summary>
        <div>{block.content || "正在思考…"}</div>
      </details>
    );
  if (block.type === "tool_use")
    return (
      <details className={"agent-tool" + (block.is_error ? " is-error" : "")}>
        <summary>
          {block.status === "streaming" ? <LoaderCircle size={13} className="spin" /> : <Wrench size={13} />}
          {block.name || "工具调用"}
          <span>{block.status === "streaming" ? "执行中" : block.is_error ? "失败" : "完成"}</span>
        </summary>
        {block.input != null && <pre>{printable(block.input)}</pre>}
        {block.output != null && <pre>{printable(block.output)}</pre>}
      </details>
    );
  return null;
}

export function AgentStream({
  session,
  active,
  onSession,
  onError,
}: {
  session: ModelingSession;
  active: boolean;
  onSession: (session: ModelingSession) => void;
  onError: (message: string) => void;
}) {
  const [state, setState] = useState<AgentStreamState>(createAgentStreamState);
  const taskId = session.dataagent_task_id;
  const sessionId = session.id;
  const workspaceId = session.workspace_id;
  const taskStatus = session.task_status;

  useEffect(() => {
    if (!active || !taskId || !["queued", "running"].includes(taskStatus)) return;
    const controller = new AbortController();
    setState(createAgentStreamState());
    let afterId = 0;
    void (async () => {
      for (let attempt = 0; !controller.signal.aborted; attempt += 1) {
        try {
          await streamSessionEvents(workspaceId, sessionId, {
            signal: controller.signal,
            afterId,
            onRecord: (record) => {
              afterId = Math.max(afterId, Number(record.seq_id || 0));
              setState((current) => processDataAgentRecord(current, record));
            },
          });
          const synced = await modelingApi.sync(workspaceId, sessionId);
          onSession(synced);
          if (!["queued", "running"].includes(synced.task_status)) return;
        } catch (error: unknown) {
          if (controller.signal.aborted) return;
          try {
            const synced = await modelingApi.sync(workspaceId, sessionId);
            onSession(synced);
            if (!["queued", "running"].includes(synced.task_status)) return;
          } catch {
            if (attempt >= 2) {
              onError(error instanceof Error ? error.message : "DataAgent 事件流中断");
              return;
            }
          }
        }
        await new Promise((resolve) =>
          window.setTimeout(resolve, Math.min(3000, 500 * 2 ** attempt)),
        );
      }
    })();
    return () => controller.abort();
  }, [active, onError, onSession, sessionId, taskId, taskStatus, workspaceId]);

  if (!taskId || !state.blocks.length) return null;
  return (
    <div className="chat-message chat-message--assistant agent-stream" aria-live="polite">
      {state.blocks.map((block) => (
        <StreamBlock key={`${block.turnIndex}:${block.blockIndex}:${block.id || block.type}`} block={block} />
      ))}
      {state.status === "streaming" && (
        <div className="agent-stream-live"><LoaderCircle size={14} className="spin" />正在流式生成</div>
      )}
      {state.status === "done" && (
        <div className="agent-stream-live"><CheckCircle2 size={14} />生成完成</div>
      )}
      {state.status === "error" && <div className="inline-error">{state.errorText || "执行失败"}</div>}
    </div>
  );
}
