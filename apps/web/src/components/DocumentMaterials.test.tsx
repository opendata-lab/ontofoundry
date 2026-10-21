import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { ManagedMaterial, Workspace } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { DocumentMaterials } from "./DocumentMaterials";

const usage = { object_types: 0, link_types: 0, properties: 0, rules: 0, metrics: 0, material_objects: 0, material_links: 0, references: [], can_delete: true };
const material = (patch: Partial<ManagedMaterial>): ManagedMaterial =>
  ({ id: "m", name: "虚构采购说明.md", byte_size: 120, chunk_count: 1, sha256: "a".repeat(64), usage, ...patch }) as ManagedMaterial;

beforeEach(() => {
  vi.spyOn(modelingApi, "materialOverview").mockResolvedValue({
    items: [
      material({ id: "doc", name: "虚构采购说明.md", origin: "upload" }),
      material({ id: "receipt", name: "表结构收据 · 虚构采购库 · 2026-10-21", origin: "table_receipt" }),
    ],
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("document materials", () => {
  it("lists uploaded documents by default and table receipts on demand", async () => {
    renderWithProviders(<DocumentMaterials workspace={{ id: "w", role: "admin" } as Workspace} />);
    expect(await screen.findByText("虚构采购说明.md")).toBeInTheDocument();
    expect(screen.queryByText("表结构收据 · 虚构采购库 · 2026-10-21")).toBeNull();
    expect(screen.getByText("1 个文档")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "文档来源" }));
    fireEvent.click(await screen.findByText("表结构收据", { selector: ".ant-select-item-option-content" }));
    expect(await screen.findByText("表结构收据 · 虚构采购库 · 2026-10-21")).toBeInTheDocument();
    expect(screen.queryByText("虚构采购说明.md")).toBeNull();
  });
});
