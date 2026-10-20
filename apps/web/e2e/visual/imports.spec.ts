import { expect, test } from "@playwright/test";
import { importPreview } from "../../src/test/importRecords";
import { mockCanvasApi, WORKSPACE_ID } from "./fixtures";

test("import upload, report expansion and explicit confirmation", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-18T02:00:00Z"));
  await mockCanvasApi(page, { emptySession: true });
  let confirmed = false;
  await page.route("**/api/v1/modeling/workspaces/*/imports/**", async (route) => {
    if (route.request().url().includes("/confirm")) { confirmed = true; await route.fulfill({ json: { session_id: "fiction-session", batch_id: "fiction-batch", report_id: importPreview.import_id } }); }
    else await route.fulfill({ json: importPreview });
  });
  await page.goto(`/workspaces/${WORKSPACE_ID}/objects`);
  await page.getByRole("button", { name: "导入", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "导入本体文件" });
  await dialog.locator('input[type="file"]').setInputFiles({ name: "fiction.json", mimeType: "application/json", buffer: Buffer.from("{}") });
  await expect(dialog.getByText("fiction.json", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "预览转换", exact: true }).click();
  await expect(dialog.getByText("保留业务对象定义")).toBeVisible();
  await dialog.getByRole("button", { name: "展开行" }).first().click();
  await expect(dialog.getByText("格式化材料第 4–12 行")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("import-preview.png", { fullPage: true });
  await dialog.getByRole("button", { name: "下一步", exact: true }).click();
  await expect(dialog.getByText("确认后将创建独立会话和待审提案")).toBeVisible();
  expect(confirmed).toBe(false);
  await expect(page).toHaveScreenshot("import-confirm.png", { fullPage: true });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "导入", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "导入", exact: true }).click();
  await expect(page.getByRole("button", { name: "预览转换", exact: true })).toBeDisabled();
});
