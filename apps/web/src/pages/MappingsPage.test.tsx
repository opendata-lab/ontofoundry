import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, catalogApi, modelingApi } from "../api/client";
import type { Assets, Draft } from "../api/types";
import { useSnapshot } from "../hooks/useSnapshot";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { MappingsPage } from "./MappingsPage";

const { open, workspace, refresh } = vi.hoisted(() => ({
  open: vi.fn(),
  refresh: vi.fn(),
  workspace: { id: "w", role: "admin", current_version: 1, version_id: "v1" },
}));
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace, refresh }) }));
vi.mock("../hooks/useElementInspector", () => ({ useElementInspector: () => ({ open }) }));
vi.mock("../hooks/useSnapshot", () => ({ useSnapshot: vi.fn() }));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn(), usePageActive: () => true }));
vi.mock("react-router-dom", () => ({ Link: ({ children }: { children: unknown }) => children }));
vi.mock("../api/client", () => ({
  api: { workspace: vi.fn() },
  modelingApi: { saveElement: vi.fn(), get: vi.fn() },
  catalogApi: { connections: vi.fn(), schemas: vi.fn(), assets: vi.fn(), refreshAssets: vi.fn() },
  ApiError: class extends Error {},
}));

let draft: Draft;
beforeEach(() => {
  vi.clearAllMocks();
  draft = example("06-inheritance");
  vi.mocked(useSnapshot).mockReturnValue({
    draft,
    error: "",
    sessionId: null,
    suffix: "",
    load: vi.fn(),
    setDraft: vi.fn(),
  });
});
afterEach(cleanup);

describe("data mapping page", () => {
  it("lists registered datasets with their usage and opens one", () => {
    renderWithProviders(<MappingsPage />);
    const parties = screen.getByRole("button", { name: "parties" }).closest("tr")!;
    expect(within(parties).getByText("6")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "parties" }));
    expect(open).toHaveBeenCalledWith({ kind: "dataset", id: draft.datasets[0].id, sessionId: null });
  });

  it("shows every object's binding mode and coverage, and filters them", () => {
    renderWithProviders(<MappingsPage />);
    fireEvent.click(screen.getByRole("tab", { name: /本体映射/ }));
    const asset = screen.getByText("资产").closest("tr")!;
    expect(within(asset).getByText("虚拟父对象")).toBeInTheDocument();
    expect(within(asset).getByText("实例来自子对象")).toBeInTheDocument();
    expect(within(screen.getByText("个人").closest("tr")!).getByText("共用父对象数据")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索对象或数据集" }), { target: { value: "vehicle" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    fireEvent.click(screen.getByText("车辆").closest("tr")!);
    expect(open).toHaveBeenCalledWith(expect.objectContaining({ kind: "object_type", tab: "properties" }));
  });

  it("registers a catalog table as a dataset through an element save", async () => {
    const assets: Assets = {
      connection_id: "c",
      version_id: "v1",
      metadata_snapshot_id: "m",
      observed_at: "2026-10-16T00:00:00Z",
      error: null,
      changes: [],
      status: "ready",
      items: [
        {
          name: "contacts",
          schema: "crm",
          comment: "联系人",
          missing: false,
          datasets: [],
          columns: [
            { name: "id", type: "bigint", primary_key: true, comment: "编号" },
            { name: "snapshot_on", type: "date", primary_key: false, comment: "快照日" },
          ],
        },
      ],
    };
    vi.mocked(catalogApi.connections).mockResolvedValue({ items: [{ id: "c", name: "主库", kind: "postgresql" } as never] });
    vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm"] });
    vi.mocked(catalogApi.assets).mockResolvedValue(assets);
    vi.mocked(api.workspace).mockResolvedValue({ version_id: "v1" } as never);
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ version: {} as never, draft, session: null });
    renderWithProviders(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "从数据目录登记" }));
    fireEvent.click(await screen.findByRole("button", { name: "登记" }));
    const form = (await screen.findAllByRole("dialog")).find((d) => d.textContent?.includes("将带入"))!;
    expect(within(form).getByRole("textbox", { name: "数据集名称" })).toHaveValue("联系人");
    fireEvent.click(within(form).getByRole("button", { name: "登记" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(payload).toMatchObject({ target_kind: "dataset", expected_current_version_id: "v1", session_id: null });
    expect(payload.draft.datasets.find((d) => d.id === payload.target_id)).toMatchObject({
      name: "联系人",
      dialect: "postgresql",
      schema_name: "crm",
      table_name: "contacts",
      columns: [
        { name: "id", physical_type: "bigint", comment: "编号" },
        { name: "snapshot_on", physical_type: "date", comment: "快照日" },
      ],
    });
    expect(refresh).toHaveBeenCalled();
  });
});
