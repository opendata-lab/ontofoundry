import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, modelingApi } from "../api/client";
import type { Workspace, WorkspaceOverview } from "../api/types";
import { draftGraph } from "../lib/semanticExplorer";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { OntologyViewPage } from "./OntologyViewPage";

const context = vi.hoisted(() => ({ workspace: {} as Workspace, refresh: vi.fn() }));
const { open } = vi.hoisted(() => ({ open: vi.fn() }));
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => context }));
vi.mock("../hooks/useElementDetail", () => ({ useElementDetail: () => ({ open: vi.fn(), href: () => "#" }) }));
// The graph opens elements in place; record what the popup was asked to show.
vi.mock("../components/elements/ElementInspector", () => ({
  ElementModal: ({ request }: { request: unknown }) => {
    open(request);
    return null;
  },
}));
vi.mock("../api/client", () => ({
  api: { overview: vi.fn(), presentation: vi.fn() },
  modelingApi: { sessions: vi.fn(), snapshot: vi.fn() },
}));
vi.mock("../components/OntologyGraph", () => ({ OntologyGraph: () => <div data-testid="semantic-graph" /> }));

const draft = example("01-basic-sales");
function overview(details: WorkspaceOverview["details"] = null): WorkspaceOverview {
  return {
    version: { version_id: "v2", version: 2, counts: { object_types: 2, link_types: 1, attributes: 8, rules: 0, metrics: 10, datasets: 2 } } as never,
    graph: draftGraph(draft),
    details,
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = { id: "w", role: "admin", current_version: 2, version_id: "v2" } as Workspace;
  vi.mocked(api.overview).mockResolvedValue(overview({ object_count: 0, link_count: 0, evidence_material_count: 0, mapping_count: 2, objects: [], links: [], mappings: [] }));
  vi.mocked(modelingApi.sessions).mockResolvedValue({ items: [] });
  vi.mocked(modelingApi.snapshot).mockResolvedValue(draft);
  vi.mocked(api.presentation).mockResolvedValue({ model: draft, version: {} as never });
});
afterEach(cleanup);
const show = () =>
  renderWithProviders(
    <MemoryRouter>
      <OntologyViewPage />
    </MemoryRouter>,
  );

describe("ontology view", () => {
  it("shows resource statistics and opens an object from the resource explorer", async () => {
    show();
    expect(await screen.findByText("资源管理器")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText("指标").some((el) => /指标\s*10/.test(el.parentElement?.textContent ?? ""))).toBe(true),
    );
    fireEvent.doubleClick(screen.getByText("客户"));
    expect(open).toHaveBeenCalledWith({ kind: "object_type", id: draft.object_types[0].id, tab: "basic", sessionId: null });
  });

  it("offers no import or export while P2 adapters are offline", async () => {
    show();
    await screen.findByText("资源管理器");
    expect(screen.queryByRole("button", { name: /导入|导出/ })).not.toBeInTheDocument();
  });

  it("reads the published snapshot for members and the presentation for readers", async () => {
    show();
    await waitFor(() => expect(modelingApi.snapshot).toHaveBeenCalledWith("w"));
    expect(await screen.findByText("订单金额")).toBeInTheDocument();
    cleanup();
    context.workspace = { ...context.workspace, role: null };
    vi.mocked(api.overview).mockResolvedValue(overview());
    show();
    await waitFor(() => expect(api.presentation).toHaveBeenCalledWith("w", "v2"));
    expect(await screen.findByText("订单金额")).toBeInTheDocument();
    expect(modelingApi.sessions).toHaveBeenCalledTimes(1);
  });

  it("points at a session whose accepted changes are not published yet", async () => {
    vi.mocked(modelingApi.sessions).mockResolvedValue({
      items: [{ id: "s1", title: "t", task_status: "idle", updated_at: "", base_version_id: "v2", has_unpublished_changes: true }],
    });
    show();
    expect(await screen.findByRole("link", { name: "有未发布的草稿修改 · 去发布" })).toHaveAttribute("href", "/delivery?session=s1");
  });

  it("does not fetch an overview for an unpublished workspace", () => {
    context.workspace = { ...context.workspace, current_version: null, version_id: null };
    show();
    expect(api.overview).not.toHaveBeenCalled();
    expect(screen.getByText("工作空间还没有已发布本体")).toBeInTheDocument();
  });
});
