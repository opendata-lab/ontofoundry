import { expect, test } from "@playwright/test";
import { INSTANCE_FACT, INSTANCE_LABEL, INSTANCE_TYPE, mockCanvasApi, REVIEW_SESSION_ID, WORKSPACE_ID } from "./fixtures";

const base = `/workspaces/${WORKSPACE_ID}`;

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.setFixedTime(new Date("2026-10-18T02:00:00Z"));
  await page.addInitScript(() => localStorage.setItem("ontofoundry.semantic.explorer.collapsed", "false"));
});

test("builder empty session aligns configuration, guidance and results", async ({ page }) => {
  await mockCanvasApi(page, { emptySession: true });
  await page.goto(`${base}/builder`);
  await expect(page.getByRole("heading", { name: "开始本体构建", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始建模", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "发布本体", exact: true })).toBeDisabled();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-empty-session.png", { fullPage: true });

  await page.getByRole("button", { name: "收起构建配置", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "业务场景描述", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "展开构建配置", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "业务场景描述", exact: true })).toBeVisible();
});

test("builder proposals retain session and material controls", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
  await expect(page.getByLabel("提案审核面板", { exact: true }).getByRole("article")).toHaveCount(3);
  await page.getByText("选择已上传材料", { exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /星河采购业务说明.md/ })).toBeChecked();
  await expect(page.getByRole("button", { name: "供应商范围修订", exact: true })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "已打开的页面" }).locator("[role=tab][aria-selected]")).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-with-proposals.png", { fullPage: true });
});

test("global overview groups layer statistics and preserves zoom controls", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/view`);
  await expect(page.getByRole("heading", { name: "语义模型层", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "适配全局图", exact: true }).click();
  await expect(page.getByLabel("全局图缩放", { exact: true })).toContainText("100%");
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("ontology-global.png", { fullPage: true });

  await page.getByRole("button", { name: "放大全局图", exact: true }).click();
  await expect(page.getByLabel("全局图缩放", { exact: true })).toContainText("120%");
});

test("semantic overview aligns resource explorer and fixed canvas", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/view`);
  await page.getByText("语义视图", { exact: true }).click();
  await expect(page.getByRole("tree")).toBeVisible();
  await expect(page.getByLabel("语义关系画布", { exact: true }).locator(".react-flow__node")).toHaveCount(11);
  await page.getByRole("button", { name: "适应画布", exact: true }).click();
  // Wait for the viewport transform to settle after fitView; fixed graph layout has no random coordinates.
  await expect
    .poll(async () => {
      const viewport = page.locator(".react-flow__viewport");
      const before = await viewport.getAttribute("style");
      await page.waitForTimeout(300);
      return (await viewport.getAttribute("style")) === before;
    })
    .toBe(true);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("ontology-semantic.png", { fullPage: true });
});

test("instance browser aligns filters, table and detail sections", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/objects/${INSTANCE_TYPE.id}/instances`);
  await expect(page.getByRole("link", { name: INSTANCE_LABEL, exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("instances-browser.png", { fullPage: true });

  await page.getByRole("link", { name: INSTANCE_LABEL, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/instances/${INSTANCE_FACT.id}$`));
  await expect(page.getByRole("heading", { name: "全部属性", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "实例图谱", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "实例图谱深度", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回详情", exact: true }).click();
  await expect(page.getByRole("heading", { name: "全部属性", exact: true })).toBeVisible();
});
