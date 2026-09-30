import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { ModelingSession } from "../api/types";
import { emptyDraft } from "../lib/draftView";
import { WorkspaceConstraints } from "./ReleaseReview";

vi.mock("../api/client", () => ({
  workspaceRequest: vi.fn(),
  modelingApi: { save: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const session = {
  id: "s",
  workspace_id: "w",
  title: "草稿",
  revision: 1,
  base_version_id: null,
  draft: { ...emptyDraft("w"), ontology_requires: ["original"] },
  graph: { workspace_id: "w", version_id: "", version_sha256: "", nodes: [], edges: [] },
  candidates: [],
  material_ids: [],
  task_status: "idle",
  task_detail: "",
  updated_at: "",
} as ModelingSession;

it("flags unsaved constraints as dirty", () => {
  const dirty = vi.fn();
  render(<WorkspaceConstraints session={session} onSaved={vi.fn()} onDirtyChange={dirty} />);
  fireEvent.click(screen.getAllByText("工作空间约束")[0]);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "edited" } });
  expect(dirty).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("status")).toHaveTextContent("尚未保存");
});

it("protects in-flight saves and reports failure without dropping edited rules", async () => {
  let reject!: (error: Error) => void;
  vi.mocked(modelingApi.save).mockImplementation(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  const busy = vi.fn(),
    saved = vi.fn();
  render(<WorkspaceConstraints session={session} onSaved={saved} onBusyChange={busy} />);
  fireEvent.click(screen.getAllByText("工作空间约束")[0]);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "  edited  " } });
  fireEvent.click(screen.getByRole("button", { name: "保存空间约束" }));
  expect(busy).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("textbox")).toBeDisabled();
  expect(modelingApi.save).toHaveBeenCalledWith(session, {
    ...session.draft,
    ontology_requires: ["edited"],
  });
  await act(async () => reject(new Error("修订冲突")));
  expect(busy).toHaveBeenLastCalledWith(false);
  expect(saved).not.toHaveBeenCalled();
  expect(screen.getByRole("textbox")).toHaveValue("  edited  ");
  expect(screen.getByRole("alert")).toHaveTextContent("修订冲突");
});
