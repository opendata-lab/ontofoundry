import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { modelingApi, workspaceRequest } from "../api/client";
import type { ModelingSession } from "../api/types";
import { ReleaseReview } from "./ReleaseReview";

vi.mock("../api/client", () => ({
  workspaceRequest: vi.fn(),
  modelingApi: { save: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const session: ModelingSession = {
  id: "s",
  workspace_id: "w",
  title: "草稿",
  revision: 1,
  base_version_id: null,
  draft: {
    schema_version: "1",
    workspace_id: "w",
    object_types: [],
    link_types: [],
    objects: [],
    links: [],
    mappings: [],
    requires: ["original"],
  },
  graph: {
    workspace_id: "w",
    version_id: "",
    version_sha256: "",
    nodes: [],
    edges: [],
  },
  candidates: [],
  material_ids: [],
  task_status: "idle",
  task_detail: "",
  updated_at: "",
};
const preview = {
  revision: 1,
  changes: [],
  impacts: [],
  ossie: {},
  validation: { publishable: true, errors: [] },
};

it("retains unsaved constraints when retrying a failed saved-revision preview", async () => {
  vi.mocked(workspaceRequest)
    .mockRejectedValueOnce(new Error("预览失败"))
    .mockResolvedValue(preview);
  const dirty = vi.fn();
  render(
    <ReleaseReview session={session} onSaved={vi.fn()} onDirtyChange={dirty} />,
  );
  fireEvent.click(screen.getByText("发布预览与变化"));
  fireEvent.click(screen.getByText("工作空间约束"));
  await screen.findByRole("alert");
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "edited" },
  });
  expect(dirty).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText(/草稿修订 1/);
  expect(screen.getByRole("textbox")).toHaveValue("edited");
  expect(screen.getByRole("status")).toHaveTextContent("尚未保存");
});

it("protects in-flight saves and reports failure without dropping edited rules", async () => {
  vi.mocked(workspaceRequest).mockResolvedValue(preview);
  let reject!: (error: Error) => void;
  vi.mocked(modelingApi.save).mockImplementation(
    () =>
      new Promise((_, no) => {
        reject = no;
      }),
  );
  const busy = vi.fn(),
    saved = vi.fn();
  render(
    <ReleaseReview session={session} onSaved={saved} onBusyChange={busy} />,
  );
  fireEvent.click(screen.getByText("工作空间约束"));
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "  edited  " },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存空间约束" }));
  expect(busy).toHaveBeenLastCalledWith(true);
  expect(screen.getByRole("textbox")).toBeDisabled();
  expect(modelingApi.save).toHaveBeenCalledWith(session, {
    ...session.draft,
    requires: ["edited"],
  });
  await act(async () => reject(new Error("修订冲突")));
  expect(busy).toHaveBeenLastCalledWith(false);
  expect(saved).not.toHaveBeenCalled();
  expect(screen.getByRole("textbox")).toHaveValue("  edited  ");
  expect(screen.getByRole("button", { name: "保存空间约束" })).toBeEnabled();
});

it("ignores a late preview for the previous saved revision", async () => {
  let old!: (value: unknown) => void;
  vi.mocked(workspaceRequest)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          old = resolve;
        }),
    )
    .mockResolvedValue({ ...preview, revision: 2 });
  const props = { session, onSaved: vi.fn() };
  const view = render(<ReleaseReview {...props} />);
  fireEvent.click(screen.getByText("发布预览与变化"));
  view.rerender(
    <ReleaseReview {...props} session={{ ...session, revision: 2 }} />,
  );
  await screen.findByText(/草稿修订 2/);
  await act(async () => old(preview));
  await waitFor(() =>
    expect(screen.queryByText(/草稿修订 1/)).not.toBeInTheDocument(),
  );
});
