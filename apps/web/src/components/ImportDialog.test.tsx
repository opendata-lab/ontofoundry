import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, importApi } from "../api/client";
import { importPreview } from "../test/importRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { ImportDialog } from "./ImportDialog";

vi.mock("../api/client", async (load) => ({ ...(await load<typeof import("../api/client")>()), importApi: { preview: vi.fn(), confirm: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());
function renderDialog() {
  const onConfirmed = vi.fn();
  const props = { open: true, workspaceId: "fiction-workspace", onClose: vi.fn(), onConfirmed };
  const view = renderWithProviders(<ImportDialog {...props} />);
  return { ...view, props, onConfirmed };
}
function chooseFile(container: HTMLElement) {
  const input = container.querySelector('input[type="file"]') ?? document.querySelector('input[type="file"]');
  fireEvent.change(input!, { target: { files: [new File(["{}"], "fiction.json", { type: "application/json" })] } });
}
describe("file import review", () => {
  it("selects locally, previews item errors and confirms with a stable request key", async () => {
    vi.mocked(importApi.preview).mockResolvedValue(importPreview);
    let resolve: (result: { session_id: string; batch_id: string; report_id: string }) => void = () => undefined;
    vi.mocked(importApi.confirm).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const { container, onConfirmed } = renderDialog();
    chooseFile(container);
    await screen.findByText("fiction.json");
    expect(importApi.preview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "预览转换" }));
    await screen.findByText("保留业务对象定义");
    expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    const button = screen.getByRole("button", { name: "生成待审提案" });
    fireEvent.click(button); fireEvent.click(button);
    expect(importApi.confirm).toHaveBeenCalledTimes(1);
    expect(importApi.confirm).toHaveBeenCalledWith("fiction-workspace", "ossie-0.2", importPreview.import_id, expect.objectContaining({ content_sha256: importPreview.content_sha256, expected_current_version_id: null, idempotency_key: expect.any(String) }));
    resolve({ session_id: "fiction-session", batch_id: "fiction-batch", report_id: importPreview.import_id });
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1));
  });
  it("blocks document errors and resets file and preview after reopening", async () => {
    vi.mocked(importApi.preview).mockResolvedValue({ ...importPreview, document_error: true });
    const { container, props, rerender } = renderDialog();
    chooseFile(container);
    await screen.findByText("fiction.json");
    fireEvent.click(screen.getByRole("button", { name: "预览转换" }));
    await screen.findByText("文件未通过校验，请修正后重新选择文件。");
    expect(screen.getByRole("button", { name: "下一步" })).toBeDisabled();
    rerender(<ImportDialog {...props} open={false} />);
    rerender(<ImportDialog {...props} open />);
    await waitFor(() => expect(screen.queryByText("保留业务对象定义")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "预览转换" })).toBeDisabled();
  });
  it("offers a fresh preview when the published head changes", async () => {
    vi.mocked(importApi.preview).mockResolvedValue(importPreview);
    vi.mocked(importApi.confirm).mockRejectedValue(new ApiError("已发布版本已变化", 409, "IMPORT_BASE_CHANGED"));
    const { container } = renderDialog();
    chooseFile(container); await screen.findByText("fiction.json");
    fireEvent.click(screen.getByRole("button", { name: "预览转换" }));
    await screen.findByText("保留业务对象定义");
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    fireEvent.click(screen.getByRole("button", { name: "生成待审提案" }));
    await screen.findByText("已发布版本已变化");
    fireEvent.click(screen.getByRole("button", { name: "重新预览" }));
    await waitFor(() => expect(importApi.preview).toHaveBeenCalledTimes(2));
  });

  it("clears the selected file and report when the workspace changes", async () => {
    vi.mocked(importApi.preview).mockResolvedValue(importPreview);
    const { container, props, rerender } = renderDialog();
    chooseFile(container); await screen.findByText("fiction.json");
    fireEvent.click(screen.getByRole("button", { name: "预览转换" }));
    await screen.findByText("保留业务对象定义");
    rerender(<ImportDialog {...props} workspaceId="other-fiction-workspace" />);
    expect(screen.queryByText("保留业务对象定义")).not.toBeInTheDocument();
    expect(screen.queryByText("fiction.json")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "预览转换" })).toBeDisabled();
  });
});
