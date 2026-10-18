import { expect, test, type Page } from "@playwright/test";
import { ELEMENTS, mockElementsApi, WORKSPACE_ID } from "./fixtures";

const base = `/workspaces/${WORKSPACE_ID}/objects`;

async function openElement(page: Page, kind: string, id: string, tab = "basic", editing = false) {
  const params = new URLSearchParams({ inspect: `${kind}:${id}`, inspectTab: tab });
  if (editing) params.set("inspectMode", "edit");
  await page.goto(`${base}?${params}`);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "复制链接", exact: true })).toBeVisible();
  await expect(dialog.getByLabel("正在读取", { exact: true })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  return dialog;
}

test.beforeEach(async ({ page }) => {
  await mockElementsApi(page);
});

test("object overview aligns key values and the relation graph", async ({ page }) => {
  const dialog = await openElement(page, "object_type", ELEMENTS.object.id);
  await expect(dialog.getByText("标题属性", { exact: true })).toBeVisible();
  await expect(dialog.locator('[role=tab][aria-selected]')).toHaveCount(5);
  await expect(page).toHaveScreenshot("element-object-overview.png", { fullPage: true });
});

test("object properties show inherited definitions and shared mapping sources", async ({ page }) => {
  const dialog = await openElement(page, "object_type", ELEMENTS.object.id, "properties");
  await expect(dialog.getByRole("heading", { name: "数据来源", exact: true })).toBeVisible();
  await expect(dialog.getByText("继承自当事人", { exact: true }).first()).toBeVisible();
  await expect(page).toHaveScreenshot("element-object-properties.png", { fullPage: true });
});

test("object property editing keeps compact inputs and the save footer", async ({ page }) => {
  const dialog = await openElement(page, "object_type", ELEMENTS.object.id, "properties", true);
  await expect(dialog.getByRole("textbox", { name: "属性名称", exact: true }).first()).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  await expect(page).toHaveScreenshot("element-object-properties-edit.png", { fullPage: true });
});

test("relation overview shows endpoints and cardinality", async ({ page }) => {
  const dialog = await openElement(page, "link_type", ELEMENTS.relation.id);
  await expect(dialog.getByText("两端", { exact: true })).toBeVisible();
  await expect(dialog.getByText("基数", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-relation-overview.png", { fullPage: true });
});

test("relation binding editor aligns each pair of endpoint properties", async ({ page }) => {
  const dialog = await openElement(page, "link_type", ELEMENTS.relation.id, "mapping", true);
  await expect(dialog.getByRole("combobox", { name: "第 1 组来源属性", exact: true })).toBeVisible();
  await expect(dialog.getByRole("combobox", { name: "第 1 组目标属性", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-relation-binding.png", { fullPage: true });
});

test("metric form displays aggregation and condition rows", async ({ page }) => {
  const dialog = await openElement(page, "metric", ELEMENTS.metric.id, "basic", true);
  await expect(dialog.getByRole("textbox", { name: "指标名称", exact: true })).toHaveValue(ELEMENTS.metric.name);
  await expect(dialog.getByRole("textbox", { name: "条件 1 的值", exact: true })).toHaveValue("VIP");
  await expect(page).toHaveScreenshot("element-metric-form.png", { fullPage: true });
});

test("metric preview displays its value and parameterized query", async ({ page }) => {
  const dialog = await openElement(page, "metric", ELEMENTS.metric.id);
  await dialog.getByRole("button", { name: "预览数值", exact: true }).click();
  await expect(dialog.getByText("1,280", { exact: true })).toBeVisible();
  await expect(dialog.getByText("参数：level = \"VIP\"", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-metric-preview.png", { fullPage: true });
});

test("dataset overview shows registered columns and the snapshot date", async ({ page }) => {
  const dialog = await openElement(page, "dataset", ELEMENTS.dataset.id);
  await expect(dialog.getByText("每日快照（stat_date）", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("columnheader", { name: "物理类型", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-dataset.png", { fullPage: true });
});

test("derived member conditions align field, operator and value", async ({ page }) => {
  const dialog = await openElement(page, "object_type", ELEMENTS.derived.id, "basic", true);
  await expect(dialog.getByRole("heading", { name: "哪些当事人属于VIP当事人", exact: true })).toBeVisible();
  await expect(dialog.getByRole("textbox", { name: "条件 1 的值", exact: true })).toHaveValue("VIP");
  await expect(page).toHaveScreenshot("element-derived-conditions.png", { fullPage: true });
});

test("instances tab displays document facts and an expanded detail section", async ({ page }) => {
  const dialog = await openElement(page, "object_type", ELEMENTS.object.id, "instances");
  await dialog.getByRole("button", { name: "张三", exact: true }).click();
  await expect(dialog.getByRole("heading", { name: "来源证据", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "收起", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-instances.png", { fullPage: true });
});

test("save impact confirmation lists dependent elements and reasons", async ({ page }) => {
  await mockElementsApi(page, { impact: true });
  const dialog = await openElement(page, "object_type", ELEMENTS.object.id, "basic", true);
  await dialog.getByRole("textbox", { name: "名称", exact: true }).fill("个人示例");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "确认保存影响", exact: true });
  await expect(confirmation.getByText("当前元素修改需要同步此依赖的定义或引用", { exact: true })).toBeVisible();
  await expect(confirmation.getByRole("button", { name: "确认保存", exact: true })).toBeEnabled();
  await expect(page).toHaveScreenshot("element-save-impact.png", { fullPage: true });
  await confirmation.getByRole("button", { name: "取消", exact: true }).click();
  await expect(dialog.getByRole("textbox", { name: "名称", exact: true })).toHaveValue("个人示例");
});
