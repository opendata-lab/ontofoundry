import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { OssieImportResult, Workspace } from "../api/types";
import { WorkspaceContextProvider } from "../hooks/useWorkspaceContext";
import { OssieImportDialog } from "./OssieImportDialog";

vi.mock("../api/client", () => ({ modelingApi: { importOssie: vi.fn() }, publishApi: {} }));
afterEach(cleanup);
it("shows reversible extension collisions without hiding them in collapsed notes", async () => {
  const note = "平台扩展碰撞：/ai_context/ontofoundry/version；导出记录原值与平台新增内容，可逆恢复原文。";
  vi.mocked(modelingApi.importOssie).mockResolvedValue({
    id: "s", title: "model", workspace_id: "w", validation: { publishable: true, errors: [], warnings: [] },
    import_report: { name: "model", description: "", mode: "merge", counts: {}, skipped: [], notes: [note] },
  } as unknown as OssieImportResult);
  render(<MemoryRouter><WorkspaceContextProvider.Provider value={{
    workspace: { id: "w", role: "admin", current_version: 1 } as Workspace,
    refresh: vi.fn(), user: { id: "u" } as never,
  }}><OssieImportDialog workspaceId="w" onClose={vi.fn()} /></WorkspaceContextProvider.Provider></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("选择 Ossie JSON 文件"), {
    target: { files: [new File(['{"version":"0.2.0.dev0"}'], "model.json", { type: "application/json" })] },
  });
  const button = screen.getByRole("button", { name: "导入 model.json" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await waitFor(() => expect(screen.getAllByRole("status").some(element => element.textContent === note)).toBe(true));
});
