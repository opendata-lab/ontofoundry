import { expect, test } from "@playwright/test";
import { ELEMENTS, INSTANCE_FACT, INSTANCE_LABEL, INSTANCE_TYPE, mockCanvasApi, REVIEW_SESSION_ID, WORKSPACE_ID } from "./fixtures";

/** Panel sizes come from ratios and sub-pixel layout; a couple of pixels is the same position. */
function expectNear(actual: number, expected: number) {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(2);
}


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
  await expect(page.getByText("点击或拖拽文件至此上传", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "展开构建配置", exact: true }).click();
  await expect(page.getByText("点击或拖拽文件至此上传", { exact: true })).toBeVisible();
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
});

test("builder draft opens element modal from model results", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
  await expect(page.getByRole("heading", { name: "供应商范围修订", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: /^本体草稿/ }).click();
  await expect(page.getByRole("button", { name: "发布本体", exact: true })).toBeEnabled();
  await expect(page.getByLabel("模型分类", { exact: true }).getByRole("button")).toHaveCount(10);
  await page.getByRole("button", { name: "供应商", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("提供商品或服务的组织", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "打开详情", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "复制链接", exact: true })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-result-modal.png", { fullPage: true });
});

test("builder shows an expanded plan in the results column", async ({ page }) => {
  await mockCanvasApi(page);
  await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
  await expect(page.getByLabel("提案审核面板", { exact: true }).getByRole("article")).toHaveCount(3);
  await expect(page.locator("dataagent-conversation").getByRole("button", { name: /计划/ })).toBeVisible();
  await page.locator("dataagent-conversation").evaluate((el) => {
    el.dispatchEvent(new CustomEvent("dataagent-plan-open", {
      cancelable: true,
      detail: {
        title: "星河采购建模计划",
        markdown: "# 星河采购建模计划\n\n## 目标\n建立供应商与采购订单。",
        body: "## 目标\n建立供应商与采购订单。\n\n## 步骤\n1. 新建对象 **供应商**，映射 `dim_supplier`\n2. 新建对象 **采购订单**，与供应商建立“供货”关系\n3. 定义指标：采购金额、订单数\n\n| 概念 | 依据 |\n| --- | --- |\n| 供应商 | 星河采购业务说明.md 第 3 行 |\n| 采购订单 | dwd_purchase_order |",
        requestId: "plan-1",
      },
    }));
  });
  await expect(page.getByRole("heading", { name: "星河采购建模计划", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-plan-panel.png", { fullPage: true });
  await page.getByRole("button", { name: "关闭计划", exact: true }).click();
  await expect(page.getByLabel("提案审核面板", { exact: true })).toBeVisible();
});

test("builder opens plan panel when clicking the plan card", async ({ page }) => {
  await mockCanvasApi(page);
  await page.route(
    (url) => url.pathname === `/api/v1/workspaces/${WORKSPACE_ID}/sessions/${REVIEW_SESSION_ID}/agent-conversation`,
    (route) =>
      route.fulfill({
        json: {
          messages: [
            {
              id: "msg-plan",
              role: "assistant",
              content: "",
              status: "success",
              blocks: [
                {
                  type: "permission_request",
                  request_id: "plan-1",
                  tool_name: "ExitPlanMode",
                  risk_level: "plan",
                  summary: [
                    "# 星河采购建模计划",
                    "",
                    "## 目标",
                    "请校验字段 `very_long_unbroken_identifier_name_that_wraps_cleanly_inside_the_plan_panel_1234567890`。",
                    "",
                    "| 概念名称 | 英文标识 | 来源材料 | 对应数据表 | 关键属性 | 备注说明 |",
                    "| --- | --- | --- | --- | --- | --- |",
                    "| 供应商 | Supplier | 星河采购业务说明.md 第 3 行 | dwd_dim_supplier_master | supplier_id, supplier_name | 主数据 |",
                    "",
                    "## 步骤",
                    ...Array.from({ length: 40 }, (_, i) => `${i + 1}. 新建对象 **供应商_${i + 1}**`),
                  ].join("\n"),
                  decision: "allow",
                },
              ],
            },
          ],
          run: null,
        },
      }),
  );
  await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
  const conversation = page.locator("dataagent-conversation");
  const planCard = conversation.locator(".dac-plan-doc");
  const planBody = conversation.locator(".dac-plan-body");
  const expandBar = conversation.locator(".dac-plan-expand-bar");
  const viewBtn = conversation.getByRole("button", { name: "查看完整计划", exact: true });
  await expect(planBody).toBeVisible();
  await expect(expandBar).toHaveCSS("opacity", "0");
  await expect(viewBtn).toHaveCSS("pointer-events", "none");

  // Clicking the card body, header, or toolbar actions keeps the body selectable and does not open PlanPanel.
  await planBody.click();
  await conversation.locator(".dac-plan-head").click();
  await conversation.locator(".dac-plan-tools").getByRole("button", { name: "复制", exact: true }).click();
  await expect(page.getByRole("toolbar", { name: "计划", exact: true })).toHaveCount(0);

  // Hovering the plan card reveals "查看完整计划", which opens the right-hand PlanPanel without expanding in place.
  await planCard.hover();
  await expect(expandBar).toHaveCSS("opacity", "1");
  await expect(viewBtn).toHaveCSS("pointer-events", "auto");
  await viewBtn.click();
  const planToolbar = page.getByRole("toolbar", { name: "计划", exact: true });
  await expect(planToolbar).toBeVisible();
  await expect(planToolbar.getByRole("heading", { name: "星河采购建模计划", exact: true })).toBeVisible();
  await expect(planBody).not.toHaveClass(/is-full/);

  // PlanPanel scrolls vertically, keeps long tokens wrapped without overflowing horizontally,
  // and keeps the wide concept table horizontally scrollable on its own.
  const scrollBox = page.locator('[role="toolbar"][aria-label="计划"] + div');
  await expect.poll(() => scrollBox.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  const overflow = await scrollBox.evaluate((el) => {
    const table = el.querySelector("table");
    return {
      panelScrollW: el.scrollWidth,
      panelClientW: el.clientWidth,
      tableScrollW: table ? table.scrollWidth : 0,
      tableClientW: table ? table.clientWidth : 0,
    };
  });
  expect(overflow.panelScrollW).toBeLessThanOrEqual(overflow.panelClientW + 1);
  expect(overflow.tableScrollW).toBeGreaterThan(overflow.tableClientW);

  const box = (await scrollBox.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, 400);
  await expect.poll(() => scrollBox.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const scrollBeforeCopy = await scrollBox.evaluate((el) => el.scrollTop);

  // Copy via plain-HTTP fallback keeps the current scroll position.
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, get: () => undefined });
  });
  await planToolbar.getByRole("button", { name: "复制计划", exact: true }).click();
  await expect.poll(() => scrollBox.evaluate((el) => el.scrollTop)).toBe(scrollBeforeCopy);

  // Closing and clicking the top-right expand button re-opens it.
  await page.getByRole("button", { name: "关闭计划", exact: true }).click();
  await expect(page.getByLabel("提案审核面板", { exact: true })).toBeVisible();
  await conversation.locator(".dac-plan-tools").getByRole("button", { name: "展开", exact: true }).click();
  await expect(planToolbar).toBeVisible();
  await expect(planToolbar.getByRole("heading", { name: "星河采购建模计划", exact: true })).toBeVisible();

  // Dragging the splitter divider resizes PlanPanel and preserves width across ModelResults and reloads.
  const rightPanel = page.locator(".builder-splitter > .ant-splitter-panel").last();
  const leftPanel = page.locator(".builder-splitter > .ant-splitter-panel").first();
  const separator = page.getByRole("separator");
  await expect(separator).toBeVisible();
  const initialRightBox = (await rightPanel.boundingBox())!;
  expectNear(initialRightBox.width, 360);

  const sepBox = (await separator.boundingBox())!;
  const startX = sepBox.x + sepBox.width / 2;
  const startY = sepBox.y + sepBox.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX - 140, startY, { steps: 10 });
  await page.mouse.up();

  await expect.poll(async () => (await rightPanel.boundingBox())!.width).toBeGreaterThan(initialRightBox.width + 120);
  const widenedRightBox = (await rightPanel.boundingBox())!;
  expect((await leftPanel.boundingBox())!.width).toBeGreaterThanOrEqual(340);

  // Closing back to ModelResults keeps the resized column width, and reloading restores it.
  await page.getByRole("button", { name: "关闭计划", exact: true }).click();
  await expect(page.getByLabel("提案审核面板", { exact: true })).toBeVisible();
  expectNear((await rightPanel.boundingBox())!.width, widenedRightBox.width);

  await page.reload();
  await expect(page.getByLabel("提案审核面板", { exact: true })).toBeVisible();
  expectNear((await rightPanel.boundingBox())!.width, widenedRightBox.width);

  // Dragging beyond bounds clamps without collapsing either panel.
  const afterReloadSep = (await separator.boundingBox())!;
  const rx = afterReloadSep.x + afterReloadSep.width / 2;
  const ry = afterReloadSep.y + afterReloadSep.height / 2;
  await page.mouse.move(rx, ry);
  await page.mouse.down();
  await page.mouse.move(rx + 400, ry, { steps: 10 });
  await page.mouse.up();
  await expect.poll(async () => (await rightPanel.boundingBox())!.width).toBeGreaterThanOrEqual(339);
  expect((await rightPanel.boundingBox())!.width).toBeLessThan(widenedRightBox.width);
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
  expectNear(after!.width, before!.width);
  expectNear(after!.x, before!.x);
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

test("builder shows a rejected result without creating a batch", async ({ page }) => {
  await mockCanvasApi(page, { proposalIssue: "failed" });
  await page.goto(`${base}/builder?session=${REVIEW_SESSION_ID}&panel=proposals`);
  await expect(page.getByText("提案结果被拒收：候选图校验未通过，请修正后重新建模")).toBeVisible();
  await expect(page.getByRole("tab", { name: /不可接受|冲突/ })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("builder-result-failed.png", { fullPage: true });
});
