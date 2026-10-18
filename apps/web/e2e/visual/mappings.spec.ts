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
