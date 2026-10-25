import { expect, test } from "@playwright/test";
import { ELEMENTS, INSTANCE_FACT, INSTANCE_LABEL, INSTANCE_TYPE, mockCanvasApi, REVIEW_SESSION_ID, WORKSPACE_ID } from "./fixtures";

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
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeDisabled();
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
  await expect(page.getByRole("heading", { name: "供应商范围修订", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "建模历史", exact: true }).click();
  const history = page.getByRole("dialog", { name: "建模历史", exact: true });
  await expect(history.getByRole("cell", { name: "供应商范围修订", exact: true })).toBeVisible();
  await history.getByRole("row").filter({ hasText: "供应商范围修订" }).click();
  await expect(history).not.toBeVisible();
  await expect(page.getByRole("tablist", { name: "已打开的页面" }).locator("[role=tab][aria-selected]")).toHaveCount(1);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-with-proposals.png", { fullPage: true });

  await page.getByRole("tab", { name: /^本体草稿/ }).click();
  await expect(page.getByRole("button", { name: "发布本体", exact: true })).toBeEnabled();
  await expect(page.getByLabel("模型分类", { exact: true }).getByRole("button")).toHaveCount(9);
  await page.getByRole("button", { name: "供应商", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("提供商品或服务的组织", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "打开详情", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "复制链接", exact: true })).toHaveCount(0);
  await expect(page).toHaveScreenshot("builder-result-modal.png", { fullPage: true });
});

test("semantic canvas releases explorer space and preserves zoom controls", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/view`);
  const canvas = page.getByLabel("语义关系画布", { exact: true });
  await expect(canvas.locator(".react-flow__node")).toHaveCount(11);
  const expanded = await canvas.boundingBox();
  await page.getByRole("button", { name: "收起资源管理器", exact: true }).click();
  await expect(page.getByRole("tree")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "展开资源管理器", exact: true })).toBeVisible();
  await expect.poll(async () => (await canvas.boundingBox())!.width).toBeGreaterThan(expanded!.width);
  // Resizing and fit view both settle in script, outside CSS animation control.
  const settled = async (read: () => Promise<unknown>) => {
    let previous: unknown = null;
    await expect.poll(async () => {
      const current = JSON.stringify(await read());
      const same = current === previous;
      previous = current;
      return same;
    }, { intervals: [250] }).toBe(true);
  };
  await settled(() => canvas.boundingBox());
  await page.getByRole("button", { name: "适应画布", exact: true }).click();
  const viewport = canvas.locator(".react-flow__viewport");
  await settled(() => viewport.getAttribute("style"));
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("ontology-semantic-collapsed.png", { fullPage: true });

  const before = await viewport.getAttribute("style");
  await page.getByRole("button", { name: "放大", exact: true }).click();
  await expect(viewport).not.toHaveAttribute("style", before!);
  await page.getByRole("button", { name: "展开资源管理器", exact: true }).click();
  await expect(page.getByRole("tree")).toBeVisible();
});

test("semantic overview aligns resource explorer and fixed canvas", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/view`);
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

  await page.getByLabel("本体资源", { exact: true }).locator(`[data-resource="${ELEMENTS.object.id}"]`).dblclick();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("标题属性", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "复制链接", exact: true })).toHaveCount(0);
  await expect(page).toHaveScreenshot("ontology-element-modal.png", { fullPage: true });
  const graphTransform = await page.locator(".react-flow__viewport").first().getAttribute("style");
  await dialog.getByRole("tab", { name: /^字段/ }).click();
  const search = dialog.getByRole("searchbox", { name: "搜索属性", exact: true });
  const table = dialog.locator(".source-fields-layout .ant-table").last();
  const before = await table.boundingBox();
  await search.fill("编号");
  await dialog.getByRole("tab", { name: /^关系/ }).click();
  await dialog.getByRole("tab", { name: /^字段/ }).click();
  await expect(search).toHaveValue("编号");
  const after = await table.boundingBox();
  expect(after!.width).toBeCloseTo(before!.width, 0);
  expect(after!.x).toBeCloseTo(before!.x, 0);
  await dialog.getByRole("button", { name: "展开弹窗", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "还原弹窗", exact: true })).toBeVisible();
  await expect(table).toBeVisible();
  await expect(page.locator(".react-flow__viewport").first()).toHaveAttribute("style", graphTransform!);

  await dialog.getByRole("button", { name: "打开详情", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/elements/object_type/${ELEMENTS.object.id}`));
  await expect(dialog).not.toBeVisible();
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

for (const issue of ["failed", "unacceptable"] as const) {
  test(`builder platform message explains ${issue} and offers retry in the conversation`, async ({ page }) => {
    await mockCanvasApi(page, { proposalIssue: issue });
    await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
    await expect(page.getByText("平台消息", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "重试", exact: true })).toBeEnabled();
    if (issue === "failed") {
      await expect(page.getByText("0 条可审，0 条受影响。", { exact: true })).toHaveCount(0);
    }
    if (issue === "unacceptable") {
      await page.getByRole("tab", { name: /不可接受/ }).click();
      await expect(page.getByLabel("提案审核面板", { exact: true }).getByRole("article")).toHaveCount(2);
    }
    await expect(page.getByText(/提案结果被拒收：/)).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`builder-platform-${issue}.png`, { fullPage: true });
  });
}
