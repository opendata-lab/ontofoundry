import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { CoreDraft } from "../../src/api/core.generated";
import type { Draft, Metric } from "../../src/api/types";

const WORKSPACE_ID = "ws-visual-demo";

function readExample(fileName: string): CoreDraft {
  const fileUrl = new URL(`../../../../docs/design/core-1-examples/${fileName}`, import.meta.url);
  const parsed = JSON.parse(readFileSync(fileUrl, "utf8")) as { draft: CoreDraft };
  return structuredClone(parsed.draft);
}

function toStoredDraft(source: CoreDraft): Draft {
  return {
    schema_version: "core-1",
    workspace_id: source.workspace_id,
    object_types: (source.object_types ?? []).map((o) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      extends: null,
      derived_by: [],
      title_property_id: null,
      ...o,
    })),
    properties: (source.properties ?? []).map((p) => ({
      description: "",
      synonyms: [],
      evidence: [],
      identifier: false,
      unique: false,
      required: false,
      ...p,
    })),
    link_types: (source.link_types ?? []).map((l) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      inverse_name: null,
      data_join: null,
      ...l,
    })),
    rules: (source.rules ?? []).map((r) => ({ description: "", evidence: [], ...r })),
    metrics: (source.metrics ?? []).map((m) => {
      const common = { description: "", synonyms: [], evidence: [] };
      if (m.kind === "simple") return { ...common, filters: [], measure: null, time_field: null, ...m } as Metric;
      if (m.kind === "expression") return { ...common, value_kind: null, time_field: null, ...m } as Metric;
      return { ...common, ...m } as Metric;
    }),
    datasets: (source.datasets ?? []).map((d) => ({
      description: "",
      dialect: null,
      schema_name: null,
      snapshot_date_column: null,
      columns: null,
      ...d,
    })),
    mappings: (source.mappings ?? []).map((m) => ({
      fields: {},
      membership_source_id: null,
      inherited_link_bindings: {},
      ...m,
      sources: (m.sources ?? []).map((s) => ({ key_columns: [], ...s })),
    })),
    material_objects: (source.material_objects ?? []).map((o) => ({ values: {}, evidence: [], ...o })),
    material_links: (source.material_links ?? []).map((l) => ({ evidence: [], ...l })),
  };
}

/**
 * Deterministic core-1 draft built from the inheritance and partial-mapping
 * examples so both tabs of MappingsPage render every visual state (registered
 * datasets, snapshot tags, metric/object counts, independent/shared/virtual/unbound
 * modes, and mapped/partial/unmapped StatusMark states).
 */
function buildMappingsDraft(): Draft {
  const inheritance = readExample("06-inheritance.json");
  const partial = readExample("10-partial.json");

  inheritance.workspace_id = WORKSPACE_ID;

  // Give one dataset a daily snapshot column so the snapshot Tag renders.
  const contracts = inheritance.datasets?.find((d) => d.name === "contracts");
  if (contracts) {
    contracts.snapshot_date_column = "stat_date";
  }

  // Leave one property unbound on `supplier` so the partial state (1/2) renders.
  const supplierMapping = inheritance.mappings?.find(
    (m) => m.id === "f3a4f071-6959-5546-8efd-2d24bb6123bc",
  );
  if (supplierMapping?.fields) {
    delete supplierMapping.fields.name;
  }

  // Append the unmapped `city` object and its identifier property from 10-partial.
  const cityObject = partial.object_types?.find((o) => o.technical_name === "city");
  const cityProps = (partial.properties ?? []).filter((p) => p.owner_type_id === cityObject?.id);
  if (cityObject) {
    inheritance.object_types = [...(inheritance.object_types ?? []), cityObject];
    inheritance.properties = [...(inheritance.properties ?? []), ...cityProps];
  }

  return toStoredDraft(inheritance);
}

const FIXTURE_DRAFT = buildMappingsDraft();

async function mockMappingsApi(page: Page) {
  // Match the backend prefix only: a "**/api/**" glob also catches Vite's
  // /src/api/*.ts modules and stops the app from loading.
  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const url = new URL(route.request().url());
    const { pathname } = url;

    if (pathname === "/api/v1/auth/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "user-visual-demo",
          username: "demo_architect",
          display_name: "林晓",
          is_platform_admin: false,
        }),
      });
      return;
    }

    if (pathname === `/api/v1/workspaces/${WORKSPACE_ID}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: WORKSPACE_ID,
          name: "星河零售示例空间",
          slug: "xinghe-retail-demo",
          description: "用于界面视觉回归测试的虚构工作空间",
          current_version: 3,
          version_id: "ver-visual-demo-3",
          created_at: "2026-10-14T08:00:00Z",
          updated_at: "2026-10-16T08:00:00Z",
          role: "admin",
        }),
      });
      return;
    }

    if (pathname === `/api/v1/workspaces/${WORKSPACE_ID}/published-snapshot`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FIXTURE_DRAFT),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    });
  });
}

test.describe("MappingsPage visual consistency", () => {
  test("datasets tab matches visual baseline", async ({ page }) => {
    const antdDeprecations: string[] = [];
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("[antd:") && text.toLowerCase().includes("deprecated")) {
        antdDeprecations.push(text);
      }
    });

    await mockMappingsApi(page);
    await page.goto(`/workspaces/${WORKSPACE_ID}/mappings`);

    await expect(page.getByRole("heading", { name: "数据映射" })).toBeVisible();
    await expect(page.getByRole("button", { name: "parties" })).toBeVisible();
    await expect(page.getByText("每日 · stat_date")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    expect(pageErrors).toEqual([]);
    expect(antdDeprecations).toEqual([]);
    await expect(page).toHaveScreenshot("mappings-datasets.png", { fullPage: true });
  });

  test("object mappings tab matches visual baseline", async ({ page }) => {
    const antdDeprecations: string[] = [];
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("console", (msg) => {
      const text = msg.text();
      if (text.includes("[antd:") && text.toLowerCase().includes("deprecated")) {
        antdDeprecations.push(text);
      }
    });

    await mockMappingsApi(page);
    await page.goto(`/workspaces/${WORKSPACE_ID}/mappings`);

    await expect(page.getByRole("heading", { name: "数据映射" })).toBeVisible();
    await page.getByRole("tab", { name: /本体映射/ }).click();

    await expect(page.getByText("当事人", { exact: true })).toBeVisible();
    await expect(page.getByText("虚拟父对象", { exact: true })).toBeVisible();
    await expect(page.getByText("已映射 1/2 个属性")).toBeVisible();
    await expect(page.getByText("未绑定数据集")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    expect(pageErrors).toEqual([]);
    expect(antdDeprecations).toEqual([]);
    await expect(page).toHaveScreenshot("mappings-objects.png", { fullPage: true });
  });
});
