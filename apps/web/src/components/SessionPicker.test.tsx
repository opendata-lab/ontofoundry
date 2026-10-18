import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { modelingSession, sessionSummary } from "../test/apiRecords";
import { SessionPicker } from "./SessionPicker";

afterEach(cleanup);

const current = modelingSession(
  { id: "running", title: "电商核心业务本体构建", task_status: "running", updated_at: "2026-09-22T07:00:00Z" },
  example("01-basic-sales"),
);

const sessions = [
  sessionSummary({
    id: "finished",
    title: "供应链模型初始化",
    task_status: "finished",
    updated_at: "2026-09-22T08:00:00Z",
  }),
  sessionSummary({
    id: "running",
    title: "电商核心业务本体构建",
    task_status: "running",
    updated_at: "2026-09-22T07:00:00Z",
  }),
];

it("opens a searchable session table, pins active work, and selects a row", () => {
  const onSelect = vi.fn();
  renderWithProviders(
    <SessionPicker session={current} sessionId="running" sessions={sessions} onSelect={onSelect} />,
  );

  const trigger = screen.getByRole("button", { name: "电商核心业务本体构建" });
  fireEvent.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  const dialog = screen.getByRole("dialog", { name: "选择建模会话" });
  // The running session comes first although the other one is newer.
  const rows = within(dialog).getAllByRole("row").filter((row) => row.getAttribute("data-row-key"));
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent("电商核心业务本体构建");
  expect(rows[0]).toHaveTextContent("运行中");
  expect(rows[0]).toHaveAttribute("aria-selected", "true");
  expect(rows[1]).toHaveTextContent("供应链模型初始化");
  expect(rows[1]).toHaveTextContent("已完成");

  fireEvent.change(within(dialog).getByRole("searchbox", { name: "搜索建模会话" }), {
    target: { value: "供应链" },
  });
  expect(within(dialog).queryByText("运行中")).not.toBeInTheDocument();
  fireEvent.click(within(dialog).getByText("供应链模型初始化"));

  expect(onSelect).toHaveBeenCalledWith("finished");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});

it("says when nothing matches and when the workspace has no sessions", () => {
  const view = renderWithProviders(
    <SessionPicker session={null} sessionId={null} sessions={sessions} onSelect={vi.fn()} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "选择建模会话" }));
  const dialog = screen.getByRole("dialog", { name: "选择建模会话" });
  fireEvent.change(within(dialog).getByRole("searchbox", { name: "搜索建模会话" }), {
    target: { value: "不存在" },
  });
  expect(within(dialog).getByText("没有匹配的会话")).toBeInTheDocument();
  view.unmount();

  renderWithProviders(<SessionPicker session={null} sessionId={null} sessions={[]} onSelect={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "选择建模会话" }));
  expect(within(screen.getByRole("dialog", { name: "选择建模会话" })).getByText("暂无建模会话")).toBeInTheDocument();
});
