import { expect, test } from "@playwright/test";
import { mockReviewApi, REVIEW_SESSION_ID, WORKSPACE_ID } from "./fixtures";

const delivery = `/workspaces/${WORKSPACE_ID}/delivery?session=${REVIEW_SESSION_ID}`;
const builder = `/workspaces/${WORKSPACE_ID}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`;

test.beforeEach(async ({ page }) => {
  // Stabilize the preview timestamp without pausing timers or UI transitions.
  await page.clock.setFixedTime(new Date("2026-10-18T02:00:00Z"));
});

test("publish checks align merge, validation and baseline states", async ({ page }) => {
  await mockReviewApi(page);
  await page.goto(delivery);
  await expect(page.getByRole("button", { name: "发布 v4", exact: true })).toBeEnabled();
  await page.getByRole("tab", { name: /^检查/ }).click();
  await expect(page.getByText("无冲突", { exact: true })).toBeVisible();
  await expect(page.getByText("0 个错误 · 1 个警告", { exact: true })).toBeVisible();
  await expect(page.getByText("供应商名称尚未绑定数据来源", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新预览", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("publish-checks.png", { fullPage: true });
});

test("version history expands the comparison with compact changes and impacts", async ({ page }) => {
  await mockReviewApi(page);
  await page.goto(`/workspaces/${WORKSPACE_ID}/delivery?tab=history`);
  await page.getByText("比较历史版本", { exact: true }).click();
  await expect(page.getByText("1 项变化 · 1 个模型内依赖", { exact: true })).toBeVisible();
  // The Select search input is covered by the selection text; click the control.
  await page.locator(".ant-select", { has: page.getByRole("combobox", { name: "比较基线" }) }).click();
  // Visible Select items are not role=option (that is a hidden a11y list).
  await page.locator(".ant-select-item-option[title=\"v2\"]").click();
  await expect(page.getByText("2 项变化 · 1 个模型内依赖", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "提供商品或服务的组织", exact: false })).toBeVisible();
  await expect(page.getByRole("cell", { name: "补充设备与车辆继承关系", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("history-comparison.png", { fullPage: true });
});

test("merge conflicts show all three sources, custom text and resolution progress", async ({ page }) => {
  await mockReviewApi(page, { conflicts: true });
  await page.goto(delivery);
  const resolver = page.getByRole("region", { name: "解决冲突" });
  await expect(resolver.getByText("提供商品的组织", { exact: true })).toBeVisible();
  await expect(resolver.getByText("经资质审核的商品供应组织", { exact: true })).toBeVisible();
  await expect(resolver.getByText("提供商品或服务的组织", { exact: true })).toBeVisible();
  await resolver.getByRole("radio", { name: /^自定义/ }).check();
  await resolver.getByRole("textbox", { name: "合并后的内容", exact: true }).fill("经资质审核、提供商品或服务的组织");
  await expect(page.getByText("已解决 1 / 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "应用到会话并重新预览", exact: true })).toBeDisabled();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("publish-conflicts.png", { fullPage: true });

  await resolver.getByRole("button", { name: "下一个", exact: true }).click();
  await resolver.getByRole("radio", { name: /^都保留/ }).check();
  await expect(page.getByText("已解决 2 / 2", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "应用到会话并重新预览", exact: true })).toBeEnabled();
});

test("proposal list groups filters, selection and compact rows in one result panel", async ({ page }) => {
  await mockReviewApi(page);
  await page.goto(builder);
  const review = page.getByLabel("提案审核面板", { exact: true });
  await expect(review.getByRole("article")).toHaveCount(3);
  await review.getByRole("checkbox", { name: "选择 供应范围", exact: true }).check();
  await expect(review.getByText("显示 3 / 6 条", { exact: true })).toBeVisible();
  await expect(review.getByText("联动 1 项", { exact: true })).toBeVisible();
  await expect(review.getByRole("searchbox", { name: "搜索提案名称" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "已打开的页面" }).locator("[role=tab][aria-selected]")).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("proposal-list.png", { fullPage: true });

  await review.getByRole("searchbox", { name: "搜索提案名称" }).fill("service_scope");
  await expect(review.getByRole("article")).toHaveCount(1);
  await review.getByRole("button", { name: "清除筛选", exact: true }).click();
  await review.getByRole("tab", { name: /^冲突\s*1$/, exact: false }).click();
  await expect(review.getByText("已过期", { exact: true })).toBeVisible();
});

test("proposal detail and evidence popover show field changes, quotes and source ids", async ({ page }) => {
  await mockReviewApi(page);
  await page.goto(builder);
  const review = page.getByLabel("提案审核面板", { exact: true });
  const row = review.locator('[data-row="proposal-visual-supplier"]');
  await row.getByRole("button", { name: "查看 供应商 的证据（2 条）", exact: true }).click();
  const evidence = page.locator(".ant-popover").filter({ hasText: "星河采购业务说明.md" });
  await expect(evidence.getByText("第 12–14 行 · 供应商范围", { exact: true })).toBeVisible();
  await evidence.getByText("来源标识", { exact: true }).click();
  await expect(evidence.getByText("material-visual-guide", { exact: true })).toBeVisible();
  await expect(evidence.getByRole("heading", { name: "人工确认", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("proposal-evidence.png", { fullPage: true });

  await row.getByRole("button", { name: "查看 供应商 的证据（2 条）", exact: true }).click();
  // Click the change text rather than the nested action controls.
  await row.getByText("提供商品或服务的组织", { exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "字段差异", exact: true })).toBeVisible();
  await expect(dialog.getByRole("cell", { name: "提供商品或服务的组织", exact: true })).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "提案理由", exact: true })).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "星河采购业务说明.md", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "接受 供应商", exact: true })).toBeEnabled();
  await expect(page).toHaveScreenshot("proposal-detail.png", { fullPage: true });
});
