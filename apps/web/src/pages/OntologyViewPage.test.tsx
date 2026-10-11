import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, modelingApi, publishApi } from "../api/client";
import type { TypeGraph, Workspace, WorkspaceOverview } from "../api/types";
import { OntologyViewPage } from "./OntologyViewPage";
import type { SelectedGraphItem } from "../components/OntologyGraph";

const context = vi.hoisted(() => ({ workspace: {} as Workspace, refresh: vi.fn() }));
vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => context,
}));
vi.mock("../api/client", () => ({
  api: { overview: vi.fn(), exportUrl: vi.fn(() => "/export") },
  modelingApi: { importOssie: vi.fn() },
  publishApi: { preview: vi.fn(), publish: vi.fn() },
}));
vi.mock("../components/OntologyGraph", () => ({
  OntologyGraph: ({ graph, onSelect }: { graph: TypeGraph; onSelect: (item: SelectedGraphItem) => void }) => (
    <div data-testid="semantic-graph" data-edges={graph.edges.length}>
      {graph.nodes.map((n) => (
        <button key={n.id} onClick={() => onSelect({ category: "node", item: n })}>{n.label}</button>
      ))}
    </div>
  ),
}));

function overview(): WorkspaceOverview {
  return {
    version: {
      workspace_id: "w",
      version_id: "v2",
      version: 2,
      version_sha256: "sha",
      status: "published",
      message: "",
      published_at: "",
      validation: {
        standard: "OSSIE",
        schema_status: "passed",
        semantic_status: "passed",
        errors: [],
        warnings: [],
        publishable: true,
      },
      counts: { object_types: 2, link_types: 1, attributes: 1 },
    },
    graph: {
      workspace_id: "w",
      version_id: "v2",
      version_sha256: "sha",
      nodes: [
        {
          id: "material",
          kind: "object_type",
          label: "物料",
          technical_name: "material",
          description: "材料定义",
          tags: ["采购"],
          attribute_count: 1,
        },
        {
          id: "supplier",
          kind: "object_type",
          label: "供应商",
          technical_name: "supplier",
          description: "",
          tags: [],
          attribute_count: 0,
        },
        {
          id: "code",
          kind: "value_type",
          label: "物料编号",
          technical_name: "code",
          description: "",
          tags: [],
        },
      ],
      edges: [
        {
          id: "supply",
          kind: "link_type",
          source: "supplier",
          target: "material",
          label: "供应",
          technical_name: "supply",
        },
        {
          id: "attr",
          kind: "attribute",
          source: "material",
          target: "code",
          label: "物料编号",
          technical_name: "code",
        },
      ],
    },
    details: {
      object_count: 0,
      link_count: 0,
      evidence_material_count: 0,
      mapping_count: 0,
      objects: [],
      links: [],
      mappings: [],
    },
  };
}
function LocationProbe() {
  return <output aria-label="查看地址">{useLocation().search}</output>;
}
function show() {
  return render(
    <MemoryRouter>
      <OntologyViewPage />
      <LocationProbe />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = {
    id: "w",
    name: "测试空间",
    slug: "test",
    description: "",
    role: "admin",
    visibility: "member",
    current_version: 1,
    version_id: "v1",
    version_sha256: "old",
    object_type_count: 2,
    link_type_count: 1,
    updated_at: "",
  };
  vi.mocked(api.overview).mockResolvedValue(overview());
});
afterEach(cleanup);

describe("本体视图", () => {
  it("defaults to four stacked layers and switches the renderer, not just a caption", async () => {
    const { container } = show();
    await screen.findByRole("region", { name: "已发布本体分层总览" });
    expect(container.querySelectorAll("[data-layer]")).toHaveLength(4);
    expect(screen.queryByTestId("semantic-graph")).not.toBeInTheDocument();
    expect(screen.getByText("v2 · 已发布")).toBeInTheDocument();
    expect(screen.getByText("业务对象 (2)")).toBeInTheDocument();
    expect(screen.getByText("暂无已发布文档实例")).toBeInTheDocument();
    expect(screen.getByText("暂无已发布数据映射")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "语义视图" }));
    for (const name of ["图谱", "业务", "技术"])
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    expect(container.querySelectorAll("[data-layer]")).toHaveLength(0);
    expect(api.exportUrl).toHaveBeenLastCalledWith("w", "v2");
    // Attributes are entity fields, so the value type and the attribute edge
    // that carries it never reach the canvas, and there is no toggle for them.
    expect(screen.queryByText("物料编号")).not.toBeInTheDocument();
    expect(screen.getByTestId("semantic-graph")).toHaveAttribute(
      "data-edges",
      "1",
    );
    expect(
      screen.queryByRole("checkbox", { name: "显示属性" }),
    ).not.toBeInTheDocument();
    // The count still comes from the published version, not from the canvas.
    expect(screen.getByText("属性 1")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "图谱标签" }), {
      target: { value: "采购" },
    });
    expect(screen.getByText("物料")).toBeInTheDocument();
    expect(screen.queryByText("供应商")).not.toBeInTheDocument();
    expect(screen.getByTestId("semantic-graph")).toHaveAttribute(
      "data-edges",
      "0",
    );
    fireEvent.click(screen.getByRole("tab", { name: "全局" }));
    expect(container.querySelectorAll("[data-layer]")).toHaveLength(4);
    expect(
      screen.getByRole("button", { name: "查看本体：供应商" }),
    ).toBeInTheDocument();
  });

  it("supports node details, layer navigation, zoom reset and keyboard tabs", async () => {
    show();
    fireEvent.click(
      await screen.findByRole("button", { name: "查看本体：物料" }),
    );
    expect(screen.getByLabelText("查看地址")).toHaveTextContent("inspect=object_type%3Amaterial");
    fireEvent.click(screen.getByRole("button", { name: "放大全局图" }));
    expect(screen.getByText("120%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "适配全局图" }));
    expect(screen.getByText("100%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "语义模型层" }));
    fireEvent.click(screen.getByRole("button", { name: "进入语义视图" }));
    expect(screen.getByRole("tab", { name: "语义视图" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "供应商" }));
    expect(screen.getByLabelText("查看地址")).toHaveTextContent("inspect=object_type%3Asupplier");
    expect(
      screen.queryByRole("link", { name: "打开本体详情" }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("tab", { name: "语义视图" }), {
      key: "ArrowLeft",
    });
    expect(screen.getByRole("tab", { name: "全局" })).toHaveFocus();
    expect(
      screen.getByRole("region", { name: "已发布本体分层总览" }),
    ).toBeInTheDocument();
  });

  it("shows real private previews only to members and keeps semantic rendering TBox-only", async () => {
    const data = overview();
    data.details = {
      object_count: 1,
      link_count: 0,
      evidence_material_count: 1,
      mapping_count: 1,
      objects: [{ id: "m001", name: "文档物料 M001", type_id: "material" }],
      links: [],
      mappings: [
        { id: "mapping", type_id: "material", table_name: "materials" },
      ],
    };
    vi.mocked(api.overview).mockResolvedValue(data);
    const { container } = show();
    await screen.findByRole("button", { name: "查看实例：文档物料 M001" });
    expect(
      screen.getByRole("button", { name: "查看映射：materials" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".layer-binding")).toHaveLength(2);
    fireEvent.click(screen.getByRole("tab", { name: "语义视图" }));
    expect(screen.queryByText("文档物料 M001")).not.toBeInTheDocument();
    expect(screen.queryByText("materials")).not.toBeInTheDocument();
  });

  it("marks nonmember layers as restricted rather than reporting misleading zero counts", async () => {
    context.workspace.role = null;
    const data = overview();
    data.details = null;
    vi.mocked(api.overview).mockResolvedValue(data);
    show();
    await screen.findByRole("region", { name: "已发布本体分层总览" });
    expect(screen.getAllByText("仅空间成员可见")).toHaveLength(4);
    expect(screen.queryByText("文档实例 (0)")).not.toBeInTheDocument();
    expect(screen.queryByText("对象映射 (0)")).not.toBeInTheDocument();
    expect(screen.queryByText("暂无已发布数据映射")).not.toBeInTheDocument();
  });

  it("does not fabricate layers or fetch unpublished workspaces", () => {
    context.workspace.current_version = null;
    show();
    expect(screen.getByText("工作空间还没有已发布本体")).toBeInTheDocument();
    expect(api.overview).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("region", { name: "已发布本体分层总览" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始建模" })).toBeInTheDocument();
  });

  it("first import: reports what it dropped and publishes as the initial version", async () => {
    context.workspace = { ...context.workspace, current_version: null } as Workspace;
    const document = {
      version: "0.2.0.dev0",
      name: "crm",
      ontology: [{ concept: "customer", type: "EntityType" }],
    };
    vi.mocked(modelingApi.importOssie).mockResolvedValue({
      id: "session-1",
      title: "导入 crm",
      import_report: {
        name: "crm",
        description: "",
        mode: "merge",
        counts: {
          objects_added: 3,
          objects_updated: 1,
          links_added: 2,
          links_updated: 0,
          attributes_added: 4,
          attributes_updated: 0,
        },
        skipped: [
          { path: "customer.sold_to", reason: "2 个 role 的关系暂不支持" },
        ],
        notes: ["合并模式：文件之外的已有对象、实例与数据映射保持不变"],
      },
    } as never);
    show();
    fireEvent.click(await screen.findByRole("tab", { name: "语义视图" }));
    fireEvent.click(screen.getByRole("button", { name: "导入" }));
    fireEvent.change(screen.getByLabelText("选择 Ossie JSON 文件"), {
      target: {
        files: [
          new File([JSON.stringify(document)], "crm.ossie.json", {
            type: "application/json",
          }),
        ],
      },
    });
    const button = await screen.findByRole("button", {
      name: /导入 crm\.ossie\.json/,
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText(/确认下方报告无误后发布为初始版本/)).toBeInTheDocument();
    // Nothing to merge with: the file is the model.
    expect(modelingApi.importOssie).toHaveBeenCalledWith("w", document, "replace");
    expect(screen.getByText("2 个 role 的关系暂不支持")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "先看草稿，稍后发布" })).toHaveAttribute(
      "href",
      "/builder?session=session-1",
    );
    expect(api.overview).not.toHaveBeenCalled();

    const preview = { validation: { publishable: true, errors: [] } };
    vi.mocked(publishApi.preview).mockResolvedValue(preview as never);
    vi.mocked(publishApi.publish).mockResolvedValue({ version: { version: 3 } } as never);
    fireEvent.click(screen.getByRole("button", { name: "确认并发布为初始版本" }));
    expect(await screen.findByText(/已发布为 v3/)).toBeInTheDocument();
    expect(publishApi.publish).toHaveBeenCalledWith(
      expect.objectContaining({ id: "session-1" }), preview, "导入 crm",
    );
    // The page refreshes only once the confirmation has been seen and closed.
    expect(context.refresh).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "完成" }));
    expect(context.refresh).toHaveBeenCalled();
  });

  it("re-import: merges by default and goes to compare and merge before publishing", async () => {
    vi.mocked(modelingApi.importOssie).mockResolvedValue({
      id: "session-2",
      title: "导入 crm",
      import_report: {
        name: "crm", description: "", mode: "merge",
        counts: { objects_added: 1, objects_updated: 2, links_added: 0, links_updated: 0,
          attributes_added: 0, attributes_updated: 1 },
        skipped: [], notes: [],
      },
    } as never);
    show();
    fireEvent.click(await screen.findByRole("tab", { name: "语义视图" }));
    fireEvent.click(screen.getByRole("button", { name: "导入" }));
    expect(screen.getByText(/空间已有 v1：导入后进入对比与合并/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("选择 Ossie JSON 文件"), {
      target: { files: [new File(['{"version":"0.2.0.dev0","name":"crm","ontology":[]}'], "crm.json")] },
    });
    const button = await screen.findByRole("button", { name: /导入 crm\.json/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText(/请对比差异并合并后发布/)).toBeInTheDocument();
    expect(vi.mocked(modelingApi.importOssie).mock.calls[0][2]).toBe("merge");
    expect(screen.getByRole("link", { name: "对比并合并" })).toHaveAttribute(
      "href",
      "/delivery?session=session-2",
    );
    expect(screen.queryByRole("button", { name: /确认并发布/ })).not.toBeInTheDocument();
    expect(publishApi.publish).not.toHaveBeenCalled();
  });

  it("offers an explicit retry without retry loops or fake fallback data", async () => {
    vi.mocked(api.overview).mockRejectedValueOnce(new Error("网络暂时不可用"));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "网络暂时不可用",
    );
    expect(api.overview).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    await waitFor(() =>
      expect(
        screen.getByRole("region", { name: "已发布本体分层总览" }),
      ).toBeInTheDocument(),
    );
    expect(api.overview).toHaveBeenCalledTimes(2);
  });
});
