import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Comparison } from "../api/types";
import { versionSummary } from "../test/apiRecords";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { HistoryComparison } from "./ReleaseReview";

vi.mock("../api/client", () => ({
  api: { comparison: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const versions = [versionSummary(2), versionSummary(1)];
const customer = example("01-basic-sales").object_types.find((o) => o.name === "customer")!;

function comparison(extra: Partial<Comparison> = {}): Comparison {
  return {
    left: versions[1],
    right: versions[0],
    changes: [
      {
        path: `object_types/${customer.id}/description`,
        kind: "changed",
        before: "企业客户",
        after: customer.description,
      },
    ],
    impacts: [{ kind: "object_type", id: customer.id, label: (customer.display_name || customer.name) }],
    ...extra,
  };
}

const open = () => fireEvent.click(screen.getByText("比较历史版本"));

it("compares the latest version with an empty baseline when opened", async () => {
  vi.mocked(api.comparison).mockResolvedValue(comparison({ left: null }));
  renderWithProviders(<HistoryComparison workspaceId="w1" versions={versions} />);
  expect(api.comparison).not.toHaveBeenCalled();

  open();
  await waitFor(() => expect(api.comparison).toHaveBeenCalledWith("w1", "v2", undefined));
  expect(await screen.findByText("1 项变化 · 1 个模型内依赖")).toBeInTheDocument();
  expect(screen.getByText(`影响：${(customer.display_name || customer.name)}`)).toBeInTheDocument();
  const row = screen.getByText(`object_types/${customer.id}/description`).closest("tr")!;
  expect(within(row).getByText("修改")).toBeInTheDocument();
  expect(within(row).getByText(`"企业客户"`)).toBeInTheDocument();
  expect(within(row).getByText(`"${customer.description}"`)).toBeInTheDocument();
});

it("compares against the chosen baseline and asks for two different versions", async () => {
  vi.mocked(api.comparison).mockResolvedValue(comparison());
  renderWithProviders(<HistoryComparison workspaceId="w1" versions={versions} />);
  open();
  await screen.findByText("1 项变化 · 1 个模型内依赖");

  fireEvent.mouseDown(screen.getByRole("combobox", { name: "比较基线" }));
  fireEvent.click(await screen.findByTitle("v1"));
  await waitFor(() => expect(api.comparison).toHaveBeenLastCalledWith("w1", "v2", "v1"));

  fireEvent.mouseDown(screen.getByRole("combobox", { name: "比较目标" }));
  const targets = await screen.findAllByTitle("v1");
  fireEvent.click(targets[targets.length - 1]);
  expect(await screen.findByText("请选择不同版本。")).toBeInTheDocument();
  expect(api.comparison).toHaveBeenCalledTimes(2);
});

it("shows why a comparison failed", async () => {
  vi.mocked(api.comparison).mockRejectedValue(new Error("版本不存在"));
  renderWithProviders(<HistoryComparison workspaceId="w1" versions={versions} />);
  open();
  expect(await screen.findByText("版本不存在")).toBeInTheDocument();
});
