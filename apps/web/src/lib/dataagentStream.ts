export type AgentBlock = {
  turnIndex: number;
  blockIndex: number;
  type: "text" | "thinking" | "tool_use";
  content: string;
  status: "streaming" | "done";
  id?: string;
  name?: string;
  input?: unknown;
  output?: unknown;
  is_error?: boolean;
};

export type AgentTurn = {
  turnIndex: number;
  turnId?: string;
  blocks: AgentBlock[];
  status: "streaming" | "done";
};

export type AgentStreamState = {
  turns: AgentTurn[];
  blocks: AgentBlock[];
  status: "idle" | "streaming" | "done" | "error";
  usage: unknown;
  errorText: string;
  afterId: number;
};

export type AgentEventType =
  | "run.started"
  | "run.completed"
  | "run.failed"
  | "run.cancelled"
  | "run.suspended"
  | "turn.started"
  | "turn.completed"
  | "content.started"
  | "content.delta"
  | "content.completed"
  | "tool.started"
  | "tool.completed"
  | "tool.denied"
  | "usage.updated";

export type DataAgentRecord = {
  seq_id?: number;
  record_type: "agent_event" | "error";
  event_type?: AgentEventType;
  data?: Record<string, unknown>;
};

export function createAgentStreamState(): AgentStreamState {
  return { turns: [], blocks: [], status: "idle", usage: null, errorText: "", afterId: 0 };
}

function cloneState(state: AgentStreamState): AgentStreamState {
  return {
    ...state,
    turns: state.turns.map((turn) => ({
      ...turn,
      blocks: turn.blocks.map((block) => ({ ...block })),
    })),
    blocks: [],
  };
}

function reindex(state: AgentStreamState) {
  state.blocks = state.turns.flatMap((turn) => turn.blocks);
}

function currentTurn(state: AgentStreamState, turnId = ""): AgentTurn {
  let turn = turnId ? state.turns.find((item) => item.turnId === turnId) : state.turns.at(-1);
  if (!turn) {
    turn = {
      turnIndex: state.turns.length,
      turnId,
      blocks: [],
      status: "streaming",
    };
    state.turns.push(turn);
  }
  return turn;
}

function addBlock(turn: AgentTurn, type: AgentBlock["type"], extra: Partial<AgentBlock> = {}) {
  const block: AgentBlock = {
    turnIndex: turn.turnIndex,
    blockIndex: turn.blocks.length,
    type,
    content: "",
    status: "streaming",
    ...extra,
  };
  turn.blocks.push(block);
  return block;
}

function agentContentBlock(state: AgentStreamState, data: Record<string, unknown>) {
  const turn = currentTurn(state, String(data.turn_id || ""));
  const type = String(data.kind || "") === "reasoning" ? "thinking" : "text";
  const contentId = String(data.content_id || "");
  let block = contentId
    ? turn.blocks.find((item) => item.id === `content:${contentId}` && item.type === type)
    : turn.blocks.at(-1);
  if (!block || block.type !== type) block = addBlock(turn, type, { id: `content:${contentId}` });
  return block;
}

function reduceAgentEvent(state: AgentStreamState, record: DataAgentRecord) {
  const type = String(record.event_type || "");
  const data = record.data || {};
  if (type === "run.started") state.status = "streaming";
  else if (type === "turn.started") {
    currentTurn(state, String(data.turn_id || ""));
  } else if (type === "content.started") {
    agentContentBlock(state, data);
  } else if (type === "content.delta") {
    agentContentBlock(state, data).content += String(data.delta || "");
  } else if (type === "content.completed") {
    const block = agentContentBlock(state, data);
    if (Object.prototype.hasOwnProperty.call(data, "text")) block.content = String(data.text || "");
    block.status = "done";
  } else if (type === "tool.started") {
    const turn = currentTurn(state, String(data.turn_id || ""));
    addBlock(turn, "tool_use", {
      id: String(data.tool_call_id || ""),
      name: String(data.tool_name || "Tool"),
      input: data.input,
    });
  } else if (type === "tool.completed" || type === "tool.denied") {
    const id = String(data.tool_call_id || "");
    const block = [...state.turns]
      .reverse()
      .flatMap((turn) => [...turn.blocks].reverse())
      .find((item) => item.type === "tool_use" && item.id === id);
    if (block) {
      block.output = type === "tool.denied" ? data.reason : data.output;
      block.is_error = type === "tool.denied" || Boolean(data.is_error);
      block.status = "done";
    }
  } else if (type === "usage.updated") state.usage = data.usage;
  else if (type === "turn.completed") {
    const turn = currentTurn(state, String(data.turn_id || ""));
    turn.status = "done";
    turn.blocks.forEach((block) => (block.status = "done"));
  } else if (type === "run.failed") {
    state.status = "error";
    state.errorText = String(data.message || data.error_code || "执行出错");
  }
  if (["run.completed", "run.cancelled", "run.suspended"].includes(type)) {
    state.status = "done";
    state.turns.forEach((turn) => {
      turn.status = "done";
      turn.blocks.forEach((block) => (block.status = "done"));
    });
  }
}

export function processDataAgentRecord(previous: AgentStreamState, record: DataAgentRecord) {
  const state = cloneState(previous);
  state.afterId = Math.max(state.afterId, Number(record.seq_id || 0));
  if (record.record_type === "agent_event") reduceAgentEvent(state, record);
  else if (record.record_type === "error") {
    state.status = "error";
    state.errorText = String(record.data?.message || "执行出错");
  }
  reindex(state);
  return state;
}

export function parseSseBuffer(buffer: string, onRecord: (record: DataAgentRecord) => void) {
  let rest = buffer.replace(/\r\n/g, "\n");
  while (true) {
    const splitAt = rest.indexOf("\n\n");
    if (splitAt < 0) break;
    const rawEvent = rest.slice(0, splitAt);
    rest = rest.slice(splitAt + 2);
    const dataLines = rawEvent
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    if (!dataLines.length) continue;
    try {
      onRecord(JSON.parse(dataLines.join("\n")) as DataAgentRecord);
    } catch {
      // A malformed event is isolated; later records remain replayable.
    }
  }
  return rest;
}

export async function streamSessionEvents(
  workspaceId: string,
  sessionId: string,
  options: {
    signal: AbortSignal;
    afterId?: number;
    onRecord: (record: DataAgentRecord) => void;
  },
) {
  const response = await fetch(
    `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/events?after_id=${options.afterId || 0}`,
    { headers: { Accept: "text/event-stream" }, credentials: "include", signal: options.signal },
  );
  if (!response.ok) throw new Error((await response.text()) || `事件流请求失败 (${response.status})`);
  if (!response.body) throw new Error("SSE 响应没有可读数据流");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = parseSseBuffer(buffer, options.onRecord);
  }
  buffer += decoder.decode();
  if (buffer.trim()) parseSseBuffer(`${buffer}\n\n`, options.onRecord);
}
