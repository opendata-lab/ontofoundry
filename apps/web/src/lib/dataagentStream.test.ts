import { describe, expect, it } from "vitest";
import {
  createAgentStreamState,
  parseSseBuffer,
  processDataAgentRecord,
  type DataAgentRecord,
} from "./dataagentStream";

describe("DataAgent event projection", () => {
  it("reassembles SSE split across arbitrary chunks", () => {
    const records: DataAgentRecord[] = [];
    let buffer = parseSseBuffer('data: {"seq_id":1,"record_', (record) => records.push(record));
    buffer = parseSseBuffer(buffer + 'type":"agent_event"}\n\n: ping\n\n', (record) => records.push(record));
    expect(buffer).toBe("");
    expect(records).toEqual([{ seq_id: 1, record_type: "agent_event" }]);
  });

  it("projects AgentEvent content deltas and tool results in order", () => {
    const records: DataAgentRecord[] = [
      { record_type: "agent_event", event_type: "run.started", data: {} },
      { record_type: "agent_event", event_type: "turn.started", data: { turn_id: "t1" } },
      { record_type: "agent_event", event_type: "content.delta", data: { turn_id: "t1", content_id: "c1", kind: "text", delta: "你好" } },
      { record_type: "agent_event", event_type: "tool.started", data: { turn_id: "t1", tool_call_id: "tool1", tool_name: "Read", input: { file_path: "a.md" } } },
      { record_type: "agent_event", event_type: "tool.completed", data: { tool_call_id: "tool1", output: "ok" } },
      { record_type: "agent_event", event_type: "run.completed", data: {} },
    ];
    const state = records.reduce(processDataAgentRecord, createAgentStreamState());
    expect(state.status).toBe("done");
    expect(state.blocks[0]).toMatchObject({ type: "text", content: "你好", status: "done" });
    expect(state.blocks[1]).toMatchObject({ type: "tool_use", name: "Read", output: "ok", status: "done" });
  });
});
