import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { metricsApi } from "../../api/client";
import type { Metric, MetricPreview as Preview } from "../../api/types";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { MetricPreview } from "./MetricPreview";

vi.mock("../../api/client", () => ({ metricsApi: { preview: vi.fn() } }));

const draft = example("01-basic-sales");
const metric = draft.metrics.find((m) => m.technical_name === "order_amount")!;
const result = (value: number, extra: Partial<Preview> = {}): Preview => ({
  definition_hash: "h",
  context_version: "v1",
  session_revision: null,
  status: "ok",
  value,
  value_kind: "decimal",
  total_query: { sql: "SELECT SUM(amount) FROM orders", params: {}, dialect: "postgresql", database: "sales" },
  snapshot_dates: [],
  warnings: [],
  ...extra,
});

function Harness() {
  const [value, setValue] = useState<Metric>(metric);
  return (
    <>
      <button onClick={() => setValue({ ...value, name: value.name + "!" } as Metric)}>改名</button>
      <button onClick={() => setValue({ ...value, aggregation: "max" } as Metric)}>改口径</button>
      <MetricPreview draft={draft} metric={value} context={{ expected_current_version_id: "v1" }} />
    </>
  );
}

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe("metric value preview", () => {
  it("previews the unsaved form and shows the value with its SQL", async () => {
    vi.mocked(metricsApi.preview).mockResolvedValue(result(1234.5));
    renderWithProviders(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /预览数值/ }));
    expect(await screen.findByText("1,234.5")).toBeInTheDocument();
    expect(screen.getByText("SELECT SUM(amount) FROM orders")).toBeInTheDocument();
    const [workspaceId, request] = vi.mocked(metricsApi.preview).mock.calls[0];
    expect(workspaceId).toBe(draft.workspace_id);
    expect(request).toMatchObject({ expected_current_version_id: "v1", metric: { id: metric.id, aggregation: "sum" } });
  });

  it("marks an earlier result as out of date once the definition changes", async () => {
    vi.mocked(metricsApi.preview).mockResolvedValue(result(10));
    renderWithProviders(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /预览数值/ }));
    await screen.findByText("10");
    fireEvent.click(screen.getByRole("button", { name: "改口径" }));
    expect(screen.getByText(/需重新预览/)).toBeInTheDocument();
  });

  it("never lets a slow older answer replace a newer one", async () => {
    let first!: (value: Preview) => void;
    vi.mocked(metricsApi.preview)
      .mockImplementationOnce(() => new Promise((resolve) => (first = resolve)))
      .mockResolvedValueOnce(result(2));
    renderWithProviders(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /预览数值/ }));
    fireEvent.click(screen.getByRole("button", { name: "改名" }));
    fireEvent.click(screen.getByRole("button", { name: /预览中/ }));
    expect(await screen.findByText("2")).toBeInTheDocument();
    await act(async () => first(result(1)));
    await waitFor(() => expect(screen.queryByText("1")).not.toBeInTheDocument());
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("explains why a valid definition cannot be previewed", async () => {
    vi.mocked(metricsApi.preview).mockResolvedValue(result(0, { status: "unable", reason_code: "engine_not_supported", value: null, total_query: null }));
    renderWithProviders(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /预览数值/ }));
    expect(await screen.findByText("无法预览：当前数据库不支持这种计算")).toBeInTheDocument();
  });
});
