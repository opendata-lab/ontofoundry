import { expect, test } from "@playwright/test";
import { mockMappingsApi, WORKSPACE_ID } from "./fixtures";

test.describe("MappingsPage visual consistency", () => {
  test("data tables tab lists registered tables and their state", async ({ page }) => {
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
    await expect(page.getByRole("cell", { name: "parties", exact: true })).toBeVisible();
    await expect(page.getByText("当前不可见或不存在")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);

    expect(pageErrors).toEqual([]);
    expect(antdDeprecations).toEqual([]);
    await expect(page).toHaveScreenshot("mappings-tables.png", { fullPage: true });
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

test("sync dialog walks through connection, schemas, tables and results", async ({ page }) => {
  await mockMappingsApi(page);
  await page.goto(`/workspaces/${WORKSPACE_ID}/mappings`);
  await expect(page.getByRole("cell", { name: "parties", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "同步数据表" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "下一步" })).toBeEnabled();
  await expect(page).toHaveScreenshot("tables-sync-connection.png");
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("checkbox", { name: "public", exact: true }).check();
  await dialog.getByRole("checkbox", { name: "fiction_archive", exact: true }).check();
  await expect(page).toHaveScreenshot("tables-sync-schemas.png");
  await dialog.getByRole("button", { name: "下一步" }).click();
  await dialog.getByRole("button", { name: "全选全部" }).click();
  await dialog.getByRole("checkbox", { name: "fiction_archive.fiction_stores" }).uncheck();
  await expect(page).toHaveScreenshot("tables-sync-tables.png");
  await dialog.getByRole("button", { name: "开始同步" }).click();
  await expect(dialog.getByText("同步完成", { exact: true })).toHaveCount(2);
  await dialog.getByText("查看每张表结果").first().click();
  await expect(page).toHaveScreenshot("tables-sync-results.png");
});
