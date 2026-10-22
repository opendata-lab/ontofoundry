import { expect, test, type Page } from "@playwright/test";
import { ELEMENTS, mockElementsApi, WORKSPACE_ID } from "./fixtures";

const base = `/workspaces/${WORKSPACE_ID}/elements`;

async function openElement(page: Page, kind: string, id: string, tab = "basic", editing = false) {
  const params = new URLSearchParams({ tab });
  if (editing) params.set("mode", "edit");
  await page.goto(`${base}/${kind}/${id}?${params}`);
  const detail = page.getByRole("tabpanel").filter({ has: page.getByRole("heading", { level: 1 }) });
  await expect(detail.getByRole("button", { name: editing ? "取消" : "编辑", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(detail.getByLabel("正在读取", { exact: true })).toHaveCount(0);
  await page.evaluate(() => document.fonts.ready);
  await expect(detail.getByRole("heading", { level: 1 })).toBeVisible();
  return detail;
}

test.beforeEach(async ({ page }) => {
  await mockElementsApi(page);
});

test("object overview aligns key values and the relation graph", async ({ page }) => {
  const detail = await openElement(page, "object_type", ELEMENTS.object.id);
  await expect(detail.getByText("标题属性", { exact: true })).toBeVisible();
  await expect(detail.locator('[role=tab][aria-selected]')).toHaveCount(4);
  await expect(detail.getByRole("tab", { name: "实例", exact: true })).toHaveCount(0);
  await expect(detail.getByRole("heading", { name: "数据来源", exact: true })).toHaveCount(0);
  await expect(detail.getByRole("region", { name: "实体实例", exact: true })).toHaveCount(0);
  await expect(page).toHaveScreenshot("element-object-overview.png", { fullPage: true });
});

test("object properties show inherited definitions and shared mapping sources", async ({ page }) => {
  const detail = await openElement(page, "object_type", ELEMENTS.object.id, "properties");
  await expect(detail.getByRole("heading", { name: "数据来源", exact: true })).toBeVisible();
  await expect(detail.getByText("继承自当事人", { exact: true }).first()).toBeVisible();
  await expect(page).toHaveScreenshot("element-object-properties.png", { fullPage: true });
});

test("object property editing keeps compact inputs and header save actions", async ({ page }) => {
  const detail = await openElement(page, "object_type", ELEMENTS.object.id, "properties", true);
  const editableNames = detail.getByRole("textbox", { name: "属性名称", exact: true });
  await expect(editableNames.first()).toBeEnabled();
  await expect(detail.getByRole("columnheader", { name: "数据绑定", exact: true })).toBeVisible();
  await expect(detail.getByRole("region", { name: "选中属性配置", exact: true })).toHaveCount(0);
  await expect(detail.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  const source = await detail.locator(".source-fields-source").boundingBox();
  const fields = await detail.locator(".source-fields-layout > section").last().boundingBox();
  const instances = await detail.getByRole("region", { name: "实体实例", exact: true }).boundingBox();
  expect(source!.x + source!.width).toBeLessThan(fields!.x);
  expect(instances!.y).toBeGreaterThanOrEqual(Math.max(source!.y + source!.height, fields!.y + fields!.height));
  for (const selector of await detail.locator(".source-fields-source .ant-select").all()) {
    const box = await selector.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(source!.x + source!.width);
  }
  await expect(page).toHaveScreenshot("element-object-properties-edit.png", { fullPage: true });
});

test("relation overview shows endpoints and cardinality", async ({ page }) => {
  const detail = await openElement(page, "link_type", ELEMENTS.relation.id);
  await expect(detail.getByRole("tab", { name: "概览", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(detail.getByLabel("正向关系", { exact: true })).toBeVisible();
  await expect(detail.getByLabel("反向关系", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-relation-overview.png", { fullPage: true });
});

test("relation binding editor aligns each pair of endpoint properties", async ({ page }) => {
  const detail = await openElement(page, "link_type", ELEMENTS.relation.id, "basic", true);
  await expect(detail.getByRole("combobox", { name: "第 1 组来源属性", exact: true })).toBeVisible();
  await expect(detail.getByRole("combobox", { name: "第 1 组目标属性", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-relation-binding.png", { fullPage: true });
});

test("metric form displays aggregation and condition rows", async ({ page }) => {
  const detail = await openElement(page, "metric", ELEMENTS.metric.id, "basic", true);
  await expect(detail.getByRole("textbox", { name: "指标名称", exact: true })).toHaveValue(ELEMENTS.metric.display_name ?? "");
  await expect(detail.getByRole("textbox", { name: "条件 1 的值", exact: true })).toHaveValue("VIP");
  await expect(page).toHaveScreenshot("element-metric-form.png", { fullPage: true });
});

test("metric preview displays its value and parameterized query", async ({ page }) => {
  const detail = await openElement(page, "metric", ELEMENTS.metric.id);
  await detail.getByRole("button", { name: "预览数值", exact: true }).click();
  await expect(detail.getByText("1,280", { exact: true })).toBeVisible();
  await expect(detail.getByText("参数：level = \"VIP\"", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-metric-preview.png", { fullPage: true });
});

test("dataset overview shows source, connection and snapshot date", async ({ page }) => {
  const detail = await openElement(page, "dataset", ELEMENTS.dataset.id);
  await expect(detail.getByText("快照日期列", { exact: true })).toBeVisible();
  await expect(detail.getByText("stat_date", { exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-dataset.png", { fullPage: true });
});

test("dataset fields place source and columns above the data preview", async ({ page }) => {
  const detail = await openElement(page, "dataset", ELEMENTS.dataset.id, "fields");
  await expect(detail.getByRole("tab", { name: "字段", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(detail.getByRole("heading", { name: "来源定义", exact: true })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "字段结构", exact: true })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "数据预览", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-dataset-fields.png", { fullPage: true });
});

test("dataset source editing waits for a database before listing tables", async ({ page }, testInfo) => {
  const detail = await openElement(page, "dataset", ELEMENTS.dataset.id, "fields", true);
  await expect(detail.getByRole("combobox", { name: "库或 schema" })).toBeVisible();
  await expect(detail.getByRole("combobox", { name: "表或视图" })).toBeDisabled();
  await page.screenshot({ path: testInfo.outputPath("element-dataset-fields-edit.png"), fullPage: true });
});

test("derived member conditions align field, operator and value", async ({ page }) => {
  const detail = await openElement(page, "object_type", ELEMENTS.derived.id, "basic", true);
  await expect(detail.getByRole("heading", { name: "哪些当事人属于VIP当事人", exact: true })).toBeVisible();
  await expect(detail.getByRole("textbox", { name: "条件 1 的值", exact: true })).toHaveValue("VIP");
  await expect(page).toHaveScreenshot("element-derived-conditions.png", { fullPage: true });
});

test("legacy instances links open the fields page facts and an expanded detail section", async ({ page }) => {
  const detail = await openElement(page, "object_type", ELEMENTS.object.id, "instances");
  await expect(detail.getByRole("tab", { name: /字段/ })).toHaveAttribute("aria-selected", "true");
  await expect(detail.getByRole("region", { name: "实体实例", exact: true })).toBeInViewport();
  await detail.getByRole("button", { name: "张三", exact: true }).click();
  await expect(detail.getByRole("heading", { name: "来源证据", exact: true })).toBeVisible();
  await expect(detail.getByRole("button", { name: "收起", exact: true })).toBeVisible();
  await expect(page).toHaveScreenshot("element-instances.png", { fullPage: true });
});

test("save impact confirmation lists dependent elements and reasons", async ({ page }) => {
  await mockElementsApi(page, { impact: true });
  const detail = await openElement(page, "object_type", ELEMENTS.object.id, "basic", true);
  await detail.getByRole("textbox", { name: "名称", exact: true }).fill("个人示例");
  await detail.getByRole("button", { name: "保存", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "确认保存影响", exact: true });
  await expect(confirmation.getByText("当前元素修改需要同步此依赖的定义或引用", { exact: true })).toBeVisible();
  await expect(confirmation.getByRole("button", { name: "确认保存", exact: true })).toBeEnabled();
  await expect(page).toHaveScreenshot("element-save-impact.png", { fullPage: true });
  await confirmation.getByRole("button", { name: "取消", exact: true }).click();
  await expect(detail.getByRole("textbox", { name: "名称", exact: true })).toHaveValue("个人示例");
});
