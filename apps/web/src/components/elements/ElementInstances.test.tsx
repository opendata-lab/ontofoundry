import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, catalogApi, instancesApi } from "../../api/client";
import type { InstanceList, MappingPreview, Workspace } from "../../api/types";
import { WorkspaceContextProvider } from "../../hooks/useWorkspaceContext";
import { InstancesPage } from "../../pages/InstancesPage";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ElementInstances } from "./ElementInstances";

/** The version and query envelope every instance read carries. */
function envelope<T extends object>(value: T) {
  return {
    workspace_id: "w",
    version_id: "v1",
    version_sha256: "",
    version_content_sha256: "",
    normalized_snapshot_sha256: "",
    queried_at: "2026-10-16T00:00:00Z",
    data_mode: "live" as const,
    quality_issues: [],
    source: "database" as const,
    truncated: false,
    depth: 1,
    snapshot_dates: [],
    ...value,
  } as never;
}

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    api: { ...original.api, workspace: vi.fn(), presentation: vi.fn() },
    modelingApi: { ...original.modelingApi, snapshot: vi.fn(), get: vi.fn() },
    catalogApi: { ...original.catalogApi, mappingPreview: vi.fn() },
    instancesApi: {
      ...original.instancesApi,
      list: vi.fn(),
      neighborhood: vi.fn(),
      draftNeighborhood: vi.fn(),
    },
  };
});

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const props = { editing: false, canEdit: true, sessionId: null, change: vi.fn(), open: vi.fn(), canBrowseDatabase: true };

describe("instances tab", () => {
  it("lists document facts by display text and shows evidence and related facts", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.technical_name === "customer")!;
    renderWithProviders(<ElementInstances {...props} draft={draft} type={customer} />);
    fireEvent.click(screen.getByRole("button", { name: "C001" }));
    const detail = screen.getByText("关联实例").closest<HTMLElement>(".ant-card")!;
    expect(within(detail).getByText("是")).toBeInTheDocument();
    expect(within(detail).getByText(/RT-0103/)).toBeInTheDocument();
  });

  it("browses database rows through a temporary mapping preview with typed keys when sessionId is present", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.technical_name === "customer")!;
    const preview: MappingPreview = {
      items: [
        {
          __key: [{ type: "string", value: "C1" }],
          __type_id: customer.id,
          __ref: "db.x",
          values: { customer_no: "C1", name: "甲公司", region: "华东" },
          display_text: "甲公司",
        },
      ],
      has_more: false,
      source: "database",
      snapshot_dates: [],
    };
    vi.mocked(catalogApi.mappingPreview).mockResolvedValue(preview);
    vi.mocked(instancesApi.draftNeighborhood).mockResolvedValue({
      center_id: "db.x",
      objects: [{ ...preview.items[0], id: "db.x", ref: "db.x", type_id: customer.id, key: preview.items[0].__key, source: "database", evidence: [] }],
      links: [],
      warnings: [],
      truncated: false,
      source: "database",
      depth: 1,
      snapshot_dates: [],
    });
    renderWithProviders(<ElementInstances {...props} sessionId="s1" draft={draft} type={customer} />);
    await waitFor(() => expect(catalogApi.mappingPreview).toHaveBeenCalled());
    expect(vi.mocked(catalogApi.mappingPreview).mock.calls[0][1]).toMatchObject({
      mapping: { type_id: customer.id },
      session_id: "s1",
      offset: 0,
      limit: 8,
    });
    fireEvent.click(await screen.findByRole("button", { name: "甲公司" }));
    await waitFor(() => expect(instancesApi.draftNeighborhood).toHaveBeenCalled());
    expect(vi.mocked(instancesApi.draftNeighborhood).mock.calls[0][1]).toMatchObject({
      type_id: customer.id,
      key: [{ type: "string", value: "C1" }],
      session_id: "s1",
      depth: 1,
    });
    expect(await screen.findByText("没有关联实例")).toBeInTheDocument();
  });

  it("browses published database instances and virtual parent union via instancesApi.list and neighborhood when sessionId is empty", async () => {
    const draft = example("06-inheritance");
    const asset = draft.object_types.find((o) => o.technical_name === "asset")!;
    const device = draft.object_types.find((o) => o.technical_name === "device")!;
    const vehicle = draft.object_types.find((o) => o.technical_name === "vehicle")!;
    const page1: InstanceList = envelope({
      items: [
        {
          id: "db.dev1",
          ref: "db.dev1",
          type_id: device.id,
          key: [{ type: "string", value: "D-01" }],
          display_text: "数控机床",
          values: { asset_no: "D-01", name: "数控机床" },
          source: "database",
          evidence: [],
        },
      ],
      next_cursor: "cursor-2",
      snapshot_dates: [{ dataset_id: "ds1", date: "2026-10-15" }],
    });
    const page2: InstanceList = envelope({
      items: [
        {
          id: "db.veh1",
          ref: "db.veh1",
          type_id: vehicle.id,
          key: [{ type: "string", value: "V-01" }],
          display_text: "叉车",
          values: { asset_no: "V-01", name: "叉车" },
          source: "database",
          evidence: [],
        },
      ],
      next_cursor: null,
      snapshot_dates: [{ dataset_id: "ds1", date: "2026-10-15" }],
    });
    vi.mocked(instancesApi.list).mockResolvedValueOnce(page1).mockResolvedValueOnce(page2);
    vi.mocked(instancesApi.neighborhood).mockResolvedValue(envelope({
      center_id: "db.dev1",
      objects: page1.items,
      links: [],
      warnings: [],
      truncated: false,
      source: "database",
      depth: 1,
      snapshot_dates: [],
    }));
    renderWithProviders(<ElementInstances {...props} sessionId={null} draft={draft} type={asset} />);
    await waitFor(() => expect(instancesApi.list).toHaveBeenCalledWith(draft.workspace_id, {
      type_id: asset.id,
      source: "database",
      q: "",
      limit: 8,
    }));
    expect(catalogApi.mappingPreview).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "数控机床" })).toBeInTheDocument();
    expect(screen.getByText("设备")).toBeInTheDocument();
    expect(screen.getByText("数据日期：2026-10-15")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "数控机床" }));
    await waitFor(() => expect(instancesApi.neighborhood).toHaveBeenCalledWith(draft.workspace_id, "db.dev1", { depth: 1 }));

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() =>
      expect(instancesApi.list).toHaveBeenLastCalledWith(draft.workspace_id, {
        type_id: asset.id,
        source: "database",
        q: "",
        cursor: "cursor-2",
        limit: 8,
      }),
    );
    expect(await screen.findByRole("button", { name: "叉车" })).toBeInTheDocument();
    expect(screen.getByText("车辆")).toBeInTheDocument();
  });

  it("allows non-member readers to browse published database instances and detail on InstancesPage", async () => {
    const fullDraft = example("06-inheritance");
    const presentationDraft = { ...fullDraft, datasets: [], mappings: [] };
    const asset = fullDraft.object_types.find((o) => o.technical_name === "asset")!;
    const device = fullDraft.object_types.find((o) => o.technical_name === "device")!;
    const workspace = { id: "w", name: "测试空间", role: null, version_id: "v1", current_version: 1 } as Workspace;
    vi.mocked(api.presentation).mockResolvedValue({ model: presentationDraft, version: { id: "v1" } as never });
    vi.mocked(instancesApi.list).mockResolvedValue(envelope({
      items: [
        {
          id: "db.dev1",
          ref: "db.dev1",
          type_id: device.id,
          key: [{ type: "string", value: "D-01" }],
          display_text: "一号机床",
          values: { asset_no: "D-01", name: "一号机床" },
          source: "database",
          evidence: [],
        },
      ],
      next_cursor: null,
      snapshot_dates: [],
    }));
    vi.mocked(instancesApi.neighborhood).mockResolvedValue(envelope({
      center_id: "db.dev1",
      objects: [
        {
          id: "db.dev1",
          ref: "db.dev1",
          type_id: device.id,
          key: [{ type: "string", value: "D-01" }],
          display_text: "一号机床",
          values: { asset_no: "D-01", name: "一号机床" },
          source: "database",
          evidence: [],
        },
      ],
      links: [],
      warnings: [],
      truncated: false,
      source: "database",
      depth: 1,
      snapshot_dates: [],
    }));
    const router = createMemoryRouter(
      [
        {
          path: "/workspaces/:workspaceId/objects/:typeId/instances/:objectId?",
          element: (
            <WorkspaceContextProvider.Provider value={{ workspace, refresh: vi.fn(), user: { id: "u" } as never }}>
              <InstancesPage />
            </WorkspaceContextProvider.Provider>
          ),
        },
      ],
      { initialEntries: [`/workspaces/w/objects/${asset.id}/instances?source=database`] },
    );
    renderWithProviders(<RouterProvider router={router} />);
    await waitFor(() =>
      expect(instancesApi.list).toHaveBeenCalledWith("w", {
        type_id: asset.id,
        source: "database",
        q: "",
        limit: 20,
      }),
    );
    const link = await screen.findByRole("link", { name: "一号机床" });
    expect(screen.getByText("设备")).toBeInTheDocument();
    fireEvent.click(link);
    await waitFor(() => expect(instancesApi.neighborhood).toHaveBeenCalledWith("w", "db.dev1", { depth: 1 }));
    expect(await screen.findByText("全部属性")).toBeInTheDocument();
  });
});
