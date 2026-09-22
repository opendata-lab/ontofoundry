import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ModelingSession, ModelingSessionSummary } from "../api/types";
import { SessionPicker } from "./SessionPicker";

function currentSession(): ModelingSession {
  return {
    id: "running",
    workspace_id: "w1",
    title: "电商核心业务本体构建",
    revision: 1,
    base_version_id: null,
    draft: {
      schema_version: "1",
      workspace_id: "w1",
      object_types: [],
      link_types: [],
      objects: [],
      links: [],
      mappings: [],
    },
    graph: {
      workspace_id: "w1",
      version_id: "",
      version_sha256: "",
      nodes: [],
      edges: [],
    },
    candidates: [],
    material_ids: [],
    task_status: "running",
    task_detail: "",
    updated_at: "2026-09-22T07:00:00Z",
  };
}

const sessions: ModelingSessionSummary[] = [
  {
    id: "finished",
    title: "供应链模型初始化",
    task_status: "finished",
    updated_at: "2026-09-22T08:00:00Z",
  },
  {
    id: "running",
    title: "电商核心业务本体构建",
    task_status: "running",
    updated_at: "2026-09-22T07:00:00Z",
  },
];

it("opens a searchable session table, pins active work, and selects a row", () => {
  const onSelect = vi.fn();
  render(
    <SessionPicker
      session={currentSession()}
      sessionId="running"
      sessions={sessions}
      onSelect={onSelect}
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: "电商核心业务本体构建" }),
  );
  const dialog = screen.getByRole("dialog", { name: "选择建模会话" });
  const rows = within(dialog).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("电商核心业务本体构建");
  expect(rows[1]).toHaveTextContent("运行中");
  expect(rows[2]).toHaveTextContent("供应链模型初始化");

  fireEvent.change(screen.getByRole("textbox", { name: "搜索建模会话" }), {
    target: { value: "供应链" },
  });
  expect(screen.queryByText("运行中")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("供应链模型初始化"));

  expect(onSelect).toHaveBeenCalledWith("finished");
  expect(
    screen.queryByRole("dialog", { name: "选择建模会话" }),
  ).not.toBeInTheDocument();
});
