import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { catalogApi, datasetApi } from "../../api/client";
import type { DatasetCheckResult, DatasetPreview, Draft } from "../../api/types";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { DatasetPanel } from "./DatasetPanel";

vi.mock("../../api/client", async (original) => {
  const actual = await original<typeof import("../../api/client")>();
  return { ...actual, catalogApi: { ...actual.catalogApi, connections: vi.fn().mockResolvedValue({ items: [] }) }, datasetApi: { ...actual.datasetApi, validate: vi.fn(), preview: vi.fn() } };
});
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

function fixture() {
  const draft = example("12-snapshot-and-trends");
  draft.datasets[0].connection_id = "fictional-test-connection";
  return draft;
}

function Fields({ initial, canPreview = true }: { initial: Draft; canPreview?: boolean }) {
  const [draft, setDraft] = useState(initial);
  return <DatasetPanel draft={draft} dataset={draft.datasets[0]} editing={false} change={setDraft} open={vi.fn()} tab="fields" canPreview={canPreview} />;
}

it("validates source, refreshes columns and previews data in the same fields pane", async () => {
  const draft = fixture();
  const columns = [{ name: "fictional_total", physical_type: "integer", comment: "示例合计" }];
  vi.mocked(datasetApi.validate).mockResolvedValue({ valid: true, diagnostics: [], columns, referenced_tables: [] });
  vi.mocked(datasetApi.preview).mockResolvedValue({ columns, items: [{ fictional_total: 42 }], limit: 20 });
  renderWithProviders(<Fields initial={draft} />);
  fireEvent.click(screen.getByRole("button", { name: "校验并探测列" }));
  expect(await screen.findByText("来源校验通过")).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "fictional_total" })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "预览前 20 行" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "预览前 20 行" }));
  expect(await screen.findByRole("cell", { name: "42" })).toBeInTheDocument();
  expect(datasetApi.preview).toHaveBeenCalledWith(draft.workspace_id, expect.objectContaining({ columns }));
});

it("keeps preview controls unavailable without data-preview permission", () => {
  renderWithProviders(<Fields initial={fixture()} canPreview={false} />);
  expect(screen.getByRole("heading", { name: "字段结构" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "预览前 20 行" })).not.toBeInTheDocument();
  expect(datasetApi.preview).not.toHaveBeenCalled();
});


it.each(["validate", "preview"] as const)("discards a hidden dataset %s response and does not start new reads", async (operation) => {
  const draft = fixture();
  const change = vi.fn();
  let resolve!: (value: DatasetCheckResult & DatasetPreview) => void;
  vi.mocked(datasetApi[operation]).mockReturnValueOnce(new Promise<DatasetCheckResult & DatasetPreview>((done) => { resolve = done; }));
  const panel = (active: boolean) => <DatasetPanel draft={draft} dataset={draft.datasets[0]} editing={false} change={change} open={vi.fn()} tab="fields" canPreview active={active} />;
  const view = renderWithProviders(panel(true));
  fireEvent.click(screen.getByRole("button", { name: operation === "validate" ? "校验并探测列" : "预览前 20 行" }));
  view.rerender(panel(false));
  await act(async () => resolve({ valid: true, diagnostics: [], referenced_tables: [], columns: [{ name: "fictional_late", physical_type: "integer", comment: "迟到列" }], items: [{ fictional_late: 999 }], limit: 20 }));
  expect(change).not.toHaveBeenCalled();
  expect(screen.queryByText("999")).not.toBeInTheDocument();
  expect(screen.queryByText("来源校验通过")).not.toBeInTheDocument();
  const calls = vi.mocked(catalogApi.connections).mock.calls.length;
  window.dispatchEvent(new Event("ontofoundry:metadata-synced"));
  await act(async () => {});
  expect(catalogApi.connections).toHaveBeenCalledTimes(calls);
  fireEvent.click(screen.getByRole("button", { name: operation === "validate" ? "校验并探测列" : "预览前 20 行" }));
  expect(datasetApi[operation]).toHaveBeenCalledTimes(1);
  view.rerender(panel(true));
  expect(screen.getByRole("button", { name: operation === "validate" ? "校验并探测列" : "预览前 20 行" })).toBeEnabled();
});
