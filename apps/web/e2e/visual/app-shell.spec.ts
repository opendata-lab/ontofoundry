import { expect, test } from "@playwright/test";
import { mockMappingsApi, WORKSPACE_ID } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockMappingsApi(page);
});

test("delivery page and its own tabs fit below the application strip", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/delivery`);
  await expect(page.getByRole("heading", { name: "本体发布" })).toBeVisible();
  await expect(page.getByText("选择待发布的本体", { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("delivery.png", { fullPage: true });
});

test("multiple open pages retain one unsaved tab and leave page tabs unchanged", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/workspaces/${WORKSPACE_ID}/mappings`);
  await expect(page.getByRole("button", { name: "parties" })).toBeVisible();
  const innerTab = page.getByRole("tab", { name: /本体映射/ });
  const innerMetrics = await innerTab.evaluate((tab) => {
    const style = getComputedStyle(tab);
    return { height: style.height, padding: style.padding, fontSize: style.fontSize, background: style.backgroundColor };
  });

  const navigation = page.getByRole("navigation", { name: "工作空间导航" });
  await navigation.getByRole("link", { name: "本体发布", exact: true }).click();
  await expect(page.getByText("选择待发布的本体", { exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "空间设置", exact: true }).click();
  await page.getByRole("textbox", { name: "空间名称", exact: true }).fill("星河零售示例空间 · 草稿");
  const strip = page.getByRole("tablist", { name: "已打开的页面" });
  await expect(strip.getByRole("tab", { name: "空间设置 未保存", exact: true })).toBeVisible();
  const scrollTop = await page.getByRole("textbox", { name: "空间名称", exact: true }).evaluate((input) => {
    const body = input.closest(".overflow-auto")!;
    body.scrollTop = 120;
    return body.scrollTop;
  });
  expect(scrollTop).toBeGreaterThan(0);
  await navigation.getByRole("link", { name: "数据映射", exact: true }).click();
  await expect(page.getByRole("button", { name: "parties" })).toBeVisible();
  await expect(strip.locator("[role=tab][aria-selected]")).toHaveCount(3);
  await expect(strip.getByLabel("未保存")).toHaveCount(1);
  expect(await innerTab.evaluate((tab) => {
    const style = getComputedStyle(tab);
    return { height: style.height, padding: style.padding, fontSize: style.fontSize, background: style.backgroundColor };
  })).toEqual(innerMetrics);

  // Close buttons also carry role="tab" in rc-tabs; count real tabs only.
  for (const tab of await strip.locator("[role=tab][aria-selected]").all()) {
    const controls = await tab.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    await expect(page.locator(`[id="${controls}"]`)).toHaveCount(1);
  }
  const panel = page.locator(`#${await strip.getByRole("tab", { name: "数据映射", exact: true }).getAttribute("aria-controls")}`);
  await expect(panel).toBeVisible();
  const table = page.getByRole("table");
  const bounds = await table.boundingBox();
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(900);
  await page.evaluate(() => document.fonts.ready);
  expect(errors).toEqual([]);
  await expect(page).toHaveScreenshot("workspace-tabs-dirty.png", { fullPage: true });

  await strip.getByRole("button", { name: "关闭 空间设置", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("关闭「空间设置」将丢失未保存的修改");
  await page.getByRole("button", { name: "返回页面", exact: true }).click();
  await strip.getByRole("tab", { name: "空间设置 未保存", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "空间名称", exact: true })).toHaveValue("星河零售示例空间 · 草稿");
  expect(await page.getByRole("textbox", { name: "空间名称", exact: true }).evaluate((input) =>
    input.closest(".overflow-auto")!.scrollTop,
  )).toBe(scrollTop);
});
