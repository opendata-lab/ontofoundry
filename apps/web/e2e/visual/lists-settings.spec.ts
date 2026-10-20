import { expect, test } from "@playwright/test";
import { mockMappingsApi, WORKSPACE_ID } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockMappingsApi(page);
});

test("object catalog keeps inherited counts, filters and detail links", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/objects`);
  await expect(page.getByRole("heading", { name: "本体对象", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "个人", exact: true })).toBeVisible();
  await expect(page.getByRole("row").filter({ has: page.getByRole("link", { name: "个人", exact: true }) }).getByRole("cell", { name: "当事人", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "英文标识", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("catalog-objects.png", { fullPage: true });

  await page.getByRole("searchbox", { name: "搜索目录" }).fill("person");
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "个人", exact: true })).toHaveAttribute("href", /elements\/object_type\//);
});

test("relation catalog aligns endpoints and multiplicity", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/relations`);
  await expect(page.getByRole("heading", { level: 1, name: "本体对象", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "signer", exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "关系含义" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("catalog-relations.png", { fullPage: true });
});

test("connections show compact rows and preserve the add action", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/connections`);
  await expect(page.getByRole("heading", { name: "数据连接", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "星河零售只读库", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "测试", exact: true })).toHaveCount(2);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("connections.png", { fullPage: true });

  await page.getByRole("button", { name: "添加连接", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "添加数据连接" })).toBeVisible();
  await expect(page.getByRole("spinbutton", { name: "端口" })).toHaveValue("5432");
});

test("settings align forms, member rows and health states", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/settings`);
  await expect(page.getByRole("heading", { name: "空间设置", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "陈宁", exact: true })).toBeVisible();
  await expect(page.getByText("未找到示例 Agent", { exact: true })).toBeAttached();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("settings.png", { fullPage: true });

  await page.getByText("未找到示例 Agent", { exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByText("需处理", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("settings-health.png", { fullPage: true });
});

test("directory shows published, unpublished and reader workspaces", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "工作空间", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /^星河零售示例空间/ })).toHaveAttribute(
    "href",
    `/workspaces/${WORKSPACE_ID}/view`,
  );
  await expect(page.getByText("尚未发布", { exact: true })).toBeVisible();
  await expect(page.getByText("仅本体可见", { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("workspace-directory.png", { fullPage: true });
});

test("delivery history keeps version messages and counts in the panel", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/delivery?tab=history`);
  await expect(page.getByRole("cell", { name: "补充设备与车辆继承关系", exact: true })).toBeVisible();
  await expect(page.getByText("比较历史版本", { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("delivery-history.png", { fullPage: true });
});

test("delivery service access uses divided sections in one panel", async ({ page }) => {
  await page.goto(`/workspaces/${WORKSPACE_ID}/delivery?tab=service`);
  await expect(page.getByRole("heading", { name: "REST API", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "MCP", exact: true })).toBeVisible();
  await expect(page.getByText("get_object", { exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("delivery-service.png", { fullPage: true });
});
