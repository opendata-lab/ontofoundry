import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    renderWithProviders(<ElementInstances {...props} draft={draft} type={customer} />);
    fireEvent.click(screen.getByRole("button", { name: "C001" }));
    const detail = screen.getByRole("region", { name: "C001的实例详情" });
    expect(within(detail).getByText("是")).toBeInTheDocument();
    expect(within(detail).getByText(/RT-0103/)).toBeInTheDocument();
  });

  it("browses database rows through a temporary mapping preview with typed keys when sessionId is present", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
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
    const asset = draft.object_types.find((o) => o.name === "asset")!;
    const device = draft.object_types.find((o) => o.name === "device")!;
    const vehicle = draft.object_types.find((o) => o.name === "vehicle")!;
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
    expect(screen.getByText(/当前数据日期：2026-10-15/)).toBeInTheDocument();

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
    const asset = fullDraft.object_types.find((o) => o.name === "asset")!;
    const device = fullDraft.object_types.find((o) => o.name === "device")!;
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


function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function databaseRows(typeId: string, label: string): InstanceList {
  return envelope({ items: [{ id: label, ref: label, type_id: typeId, source: "database", key: [{ type: "string", value: label }], display_text: label, values: {}, evidence: [] }], next_cursor: null });
}

const tick = () => act(() => vi.advanceTimersByTimeAsync(300));

describe("retained instance panel lifecycle", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it.each([null, "s1"])("does not start hidden or debounced requests (session %s)", async (sessionId) => {
    const draft = example("01-basic-sales");
    const type = draft.object_types[0];
    const view = renderWithProviders(<ElementInstances {...props} draft={draft} type={type} sessionId={sessionId} active={false} />);
    await tick();
    expect(instancesApi.list).not.toHaveBeenCalled();
    expect(catalogApi.mappingPreview).not.toHaveBeenCalled();
    view.rerender(<ElementInstances {...props} draft={draft} type={type} sessionId={sessionId} active />);
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索实例" }), { target: { value: "星舟" } });
    view.rerender(<ElementInstances {...props} draft={draft} type={type} sessionId={sessionId} active={false} />);
    await tick();
    expect(instancesApi.list).not.toHaveBeenCalled();
    expect(catalogApi.mappingPreview).not.toHaveBeenCalled();
  });

  it.each(["resolve", "reject"] as const)("discards a hidden list %s and resumes the same search", async (outcome) => {
    const draft = example("01-basic-sales");
    const type = draft.object_types[0];
    const old = deferred<InstanceList>();
    vi.mocked(instancesApi.list).mockReturnValueOnce(old.promise).mockResolvedValue(databaseRows(type.id, "新结果"));
    const view = renderWithProviders(<ElementInstances {...props} draft={draft} type={type} active />);
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索实例" }), { target: { value: "星舟" } });
    await tick();
    expect(instancesApi.list).toHaveBeenCalledTimes(1);
    view.rerender(<ElementInstances {...props} draft={draft} type={type} active={false} />);
    await act(async () => {
      if (outcome === "resolve") old.resolve(databaseRows(type.id, "旧结果"));
      else old.reject(new Error("旧错误"));
    });
    expect(screen.queryByText("旧结果")).not.toBeInTheDocument();
    expect(screen.queryByText(/旧错误/)).not.toBeInTheDocument();
    await tick();
    expect(instancesApi.list).toHaveBeenCalledTimes(1);
    view.rerender(<ElementInstances {...props} draft={draft} type={type} active />);
    expect(screen.getByRole("searchbox", { name: "搜索实例" })).toHaveValue("星舟");
    await tick();
    expect(screen.getByRole("button", { name: "新结果" })).toBeInTheDocument();
    expect(instancesApi.list).toHaveBeenLastCalledWith(draft.workspace_id, expect.objectContaining({ q: "星舟" }));
  });

  it.each(["element", "version"])("resets selection and search on %s changes and rejects an older list", async (change) => {
    const draft = example("01-basic-sales");
    const firstType = draft.object_types[0];
    const nextType = change === "element" ? draft.object_types[1] : firstType;
    const old = deferred<InstanceList>();
    vi.mocked(instancesApi.list).mockReturnValueOnce(old.promise).mockResolvedValue(databaseRows(nextType.id, "当前结果"));
    const view = renderWithProviders(<ElementInstances {...props} draft={draft} type={firstType} readScope="v1" />);
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索实例" }), { target: { value: "旧筛选" } });
    await tick();
    view.rerender(<ElementInstances {...props} draft={draft} type={nextType} readScope={change === "version" ? "v2" : "v1"} />);
    expect(screen.getByRole("searchbox", { name: "搜索实例" })).toHaveValue("");
    await tick();
    await act(async () => old.resolve(databaseRows(firstType.id, "迟到结果")));
    expect(screen.getByRole("button", { name: "当前结果" })).toBeInTheDocument();
    expect(screen.queryByText("迟到结果")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "选中实例详情" })).not.toBeInTheDocument();
  });

  it.each(["hide", "version", "element"])("discards an older neighborhood after %s and resumes without a stuck spinner", async (change) => {
    const draft = example("01-basic-sales");
    const type = draft.object_types[0];
    const old = deferred<Awaited<ReturnType<typeof instancesApi.neighborhood>>>();
    vi.mocked(instancesApi.list).mockResolvedValue(databaseRows(type.id, "星舟一号"));
    vi.mocked(instancesApi.neighborhood).mockReturnValueOnce(old.promise).mockResolvedValue(envelope({ center_id: "星舟一号", objects: [], links: [] }));
    const view = renderWithProviders(<ElementInstances {...props} draft={draft} type={type} readScope="v1" active />);
    await tick();
    fireEvent.click(screen.getByRole("button", { name: "星舟一号" }));
    expect(instancesApi.neighborhood).toHaveBeenCalledTimes(1);
    view.rerender(<ElementInstances {...props} draft={draft} type={change === "element" ? draft.object_types[1] : type} readScope={change === "version" ? "v2" : "v1"} active={change !== "hide"} />);
    await act(async () => old.reject(new Error("旧关联错误")));
    expect(screen.queryByText("旧关联错误")).not.toBeInTheDocument();
    if (change === "hide") {
      view.rerender(<ElementInstances {...props} draft={draft} type={type} readScope="v1" active />);
      await tick();
      expect(instancesApi.neighborhood).toHaveBeenCalledTimes(2);
      expect(screen.getByText("没有关联实例")).toBeInTheDocument();
      expect(screen.queryByText("正在读取关联实例…")).not.toBeInTheDocument();
    } else {
      expect(screen.queryByText("星舟一号的实例详情")).not.toBeInTheDocument();
    }
  });

  it("rejects a hidden mapping preview even after a newer preview completes", async () => {
    const draft = example("01-basic-sales");
    const type = draft.object_types[0];
    const old = deferred<MappingPreview>();
    const preview = (label: string): MappingPreview => ({ items: [{ __ref: label, __type_id: type.id, __key: [{ type: "string", value: label }], display_text: label, values: {} }], has_more: false, snapshot_dates: [], source: "database" });
    vi.mocked(catalogApi.mappingPreview).mockReturnValueOnce(old.promise).mockResolvedValue(preview("当前预览"));
    const view = renderWithProviders(<ElementInstances {...props} sessionId="s1" draft={draft} type={type} active />);
    await tick();
    view.rerender(<ElementInstances {...props} sessionId="s1" draft={draft} type={type} active={false} />);
    view.rerender(<ElementInstances {...props} sessionId="s1" draft={draft} type={type} active />);
    await tick();
    await act(async () => old.resolve(preview("迟到预览")));
    expect(screen.getByRole("button", { name: "当前预览" })).toBeInTheDocument();
    expect(screen.queryByText("迟到预览")).not.toBeInTheDocument();
  });
});
