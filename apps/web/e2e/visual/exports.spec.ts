import { expect, test } from "@playwright/test";
import { importPreview } from "../../src/test/importRecords";
import { mockMappingsApi, WORKSPACE_ID } from "./fixtures";

test("export selected history version, report hash and unavailable Ossie", async ({ page }) => {
  await mockMappingsApi(page);
  await page.route("**/api/v1/modeling/workspaces/*/exports/**", async (route) => {
    const url = new URL(route.request().url());
    const unavailable = url.pathname.endsWith("ossie-0.2");
    await route.fulfill({ json: {
      version_id: url.searchParams.get("version_id"), adapter: unavailable ? "ossie-0.2" : "ontofoundry-core-1-package",
      filename: "fictional-v3.ontofoundry.zip", media_type: "application/zip",
      content_sha256: unavailable ? null : "a".repeat(64), download_url: unavailable ? null : "/fictional-artifact/" + "a".repeat(64),
      report: { ...importPreview.report, direction: "export", issues: [importPreview.report.issues[unavailable ? 1 : 0]] },
    } });
  });
  await page.goto(`/workspaces/${WORKSPACE_ID}/delivery?tab=history`);
  await page.getByRole("button", { name: "导出此版本", exact: true }).first().click();
  const dialog = page.getByRole("dialog", { name: "导出本体文件" });
  await dialog.getByRole("button", { name: "生成导出报告", exact: true }).click();
  await expect(dialog.getByRole("link", { name: "下载文件" })).toHaveAttribute("href", "/fictional-artifact/" + "a".repeat(64));
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveScreenshot("export-native.png", { fullPage: true });
  await dialog.locator(".ant-select", { has: page.getByRole("combobox", { name: "导出格式" }) }).click();
  await page.locator('.ant-select-item-option[title="Apache Ossie 0.2（ZIP + 扩展文件）"]').click();
  await expect(dialog.getByRole("link", { name: "下载文件" })).toHaveCount(0);
  await dialog.getByRole("button", { name: /生成导出报告/ }).click();
  await expect(dialog.getByText("当前格式无法完整交付，未生成可下载文件")).toBeVisible();
  await expect(page).toHaveScreenshot("export-unavailable.png", { fullPage: true });
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(dialog).not.toBeVisible();
});
