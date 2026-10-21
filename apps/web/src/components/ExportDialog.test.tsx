import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, exportApi } from "../api/client";
import type { ExportPreview } from "../api/types";
import { versionSummary } from "../test/apiRecords";
import { importPreview } from "../test/importRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { ExportDialog } from "./ExportDialog";
vi.mock("../api/client", async (load) => ({ ...(await load<typeof import("../api/client")>()), exportApi: { preview: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
const preview: ExportPreview = { version_id: "fiction-version", adapter: "ontofoundry-core-1-package", report: { ...importPreview.report, direction: "export", issues: [importPreview.report.issues[0]], content_sha256: "a".repeat(64) }, content_sha256: "a".repeat(64), filename: "fiction.ontofoundry.zip", media_type: "application/zip", download_url: "/fiction-artifact/" + "a".repeat(64) };
function renderDialog() {
  const props = { open: true, workspaceId: "fiction-workspace", versions: [versionSummary(2, { version_id: "fiction-version" })], onClose: vi.fn() };
  return { ...renderWithProviders(<ExportDialog {...props} />), props };
}
it("requires a report and downloads exactly the shown artifact", async () => {
  vi.mocked(exportApi.preview).mockResolvedValue(preview);
  renderDialog();
  expect(screen.queryByRole("link", { name: "下载文件" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  expect(await screen.findByRole("link", { name: "下载文件" })).toHaveAttribute("href", preview.download_url);
  expect(screen.getByText(preview.content_sha256!)).toBeInTheDocument();
  expect(exportApi.preview).toHaveBeenCalledWith("fiction-workspace", "ontofoundry-core-1-package", "fiction-version");
});
it("does not offer a file for export errors or permission failures", async () => {
  vi.mocked(exportApi.preview).mockResolvedValue({ ...preview, download_url: null, content_sha256: null, report: { ...preview.report, issues: [importPreview.report.issues[1]] } });
  renderDialog();
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  expect(await screen.findByText("当前格式无法完整交付，未生成可下载文件")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "下载文件" })).not.toBeInTheDocument();
  vi.mocked(exportApi.preview).mockRejectedValue(new ApiError("需要映射读取授权", 403, "MAPPINGS_FORBIDDEN"));
  fireEvent.click(screen.getByRole("button", { name: "重新生成报告" }));
  expect(await screen.findByText("需要映射读取授权")).toBeInTheDocument();
});
it("clears the old download when format changes and on reopening", async () => {
  vi.mocked(exportApi.preview).mockResolvedValue(preview);
  const { props, rerender } = renderDialog();
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  await screen.findByRole("link", { name: "下载文件" });
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "导出格式" }));
  fireEvent.click(await screen.findByText("Apache Ossie 0.2（ZIP + 扩展文件）", { selector: ".ant-select-item-option-content" }));
  expect(screen.queryByRole("link", { name: "下载文件" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成导出报告" })).toBeEnabled();
  rerender(<ExportDialog {...props} open={false} />);
  rerender(<ExportDialog {...props} open />);
  await waitFor(() => expect(screen.queryByText(preview.filename)).not.toBeInTheDocument());
});

it("ignores an earlier report after changing the selected version", async () => {
  let finish!: (value: ExportPreview) => void;
  vi.mocked(exportApi.preview).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  renderWithProviders(<ExportDialog open workspaceId="fiction-workspace" versions={[versionSummary(2, { version_id: "fiction-version" }), versionSummary(1, { version_id: "older-fiction-version" })]} onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "导出版本" }));
  fireEvent.click(await screen.findByText("v1", { selector: ".ant-select-item-option-content" }));
  finish(preview);
  await waitFor(() => expect(screen.getByRole("button", { name: "生成导出报告" })).toBeEnabled());
  expect(screen.queryByRole("link", { name: "下载文件" })).not.toBeInTheDocument();
  vi.mocked(exportApi.preview).mockResolvedValue({ ...preview, version_id: "older-fiction-version" });
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  await screen.findByRole("link", { name: "下载文件" });
  expect(exportApi.preview).toHaveBeenLastCalledWith("fiction-workspace", "ontofoundry-core-1-package", "older-fiction-version");
});

it("removes an earlier download when authorization fails on regeneration", async () => {
  vi.mocked(exportApi.preview).mockResolvedValue(preview);
  renderDialog();
  fireEvent.click(screen.getByRole("button", { name: "生成导出报告" }));
  await screen.findByRole("link", { name: "下载文件" });
  vi.mocked(exportApi.preview).mockRejectedValue(new ApiError("需要映射读取授权", 403));
  fireEvent.click(screen.getByRole("button", { name: "重新生成报告" }));
  await screen.findByText("需要映射读取授权");
  expect(screen.queryByRole("link", { name: "下载文件" })).not.toBeInTheDocument();
});
