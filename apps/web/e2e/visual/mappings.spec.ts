import { expect, test } from "@playwright/test";
import { mockMappingsApi, WORKSPACE_ID } from "./fixtures";

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

    await expect(page.getByRole("heading", { name: "数据管理" })).toBeVisible();
    await expect(page.getByRole("button", { name: "parties" })).toBeVisible();
    await expect(page.getByText("每日 · stat_date")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    expect(pageErrors).toEqual([]);
    expect(antdDeprecations).toEqual([]);
    await expect(page).toHaveScreenshot("mappings-datasets.png", { fullPage: true });
  });

  test("object mapping details preserve virtual, partial and unbound states", async ({ page }) => {
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
    // The catalog's data mapping column lists every binding state in one place.
    await page.goto(`/workspaces/${WORKSPACE_ID}/objects`);
    const state = (name: string) => page.getByRole("row").filter({ has: page.getByRole("link", { name, exact: true }) });
    await expect(state("资产")).toContainText("虚拟父对象，实例来自子对象");
    await expect(state("供应商")).toContainText("已映射 1/2 个属性");
    await expect(state("城市")).toContainText("未绑定数据集");
    await page.evaluate(() => document.fonts.ready);

    expect(pageErrors).toEqual([]);
    expect(antdDeprecations).toEqual([]);
    await expect(page).toHaveScreenshot("mappings-objects.png", { fullPage: true });
  });
});
