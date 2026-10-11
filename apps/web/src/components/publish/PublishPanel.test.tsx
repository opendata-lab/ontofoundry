import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, publishApi } from "../../api/client";
import type { MergeConflict, ModelingSession, PublishPreview } from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { lineDiff } from "../../lib/lineDiff";
import { PublishPanel } from "./PublishPanel";
import { MemoryRouter } from "react-router-dom";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const session = {
  id: "s",
  workspace_id: "w",
  revision: 4,
  base_version_id: "v1",
  draft: emptyDraft("w"),
} as unknown as ModelingSession;

function preview(extra: Partial<PublishPreview> = {}): PublishPreview {
  return {
    session_revision: 4,
    base_version_id: "v1",
    base_version_number: 1,
    current_version_id: "v2",
    current_version_number: 2,
    next_version_number: 3,
    current_version_sha256: "c".repeat(64),
    merged_snapshot_sha256: "m".repeat(64),
    validation: {
      standard: "",
      schema_status: "passed",
      semantic_status: "passed",
      errors: [],
      warnings: [],
      publishable: true,
    },
    changes: [
      {
        element_kind: "object_type",
        element_id: "t",
        label: "供应商",
        change: "updated",
        field_changes: [{ path: "description", before: "旧定义", after: "新定义" }],
        before: {},
        after: {},
      },
      {
        element_kind: "action",
        element_id: "a",
        label: "审批供应商",
        change: "created",
        field_changes: [],
        before: null,
        after: {},
      },
    ],
    requires_change: null,
    labels: {},
    impacts: [],
    auto_merged: [
      {
        element_kind: "object_type",
        element_id: "x",
        label: "物料",
        change: "updated",
        field_changes: [],
        before: {},
        after: {},
        side: "latest",
      },
    ],
    ossie: { version: "0.2.0.dev0" },
    ...extra,
  };
}

const conflict: MergeConflict = {
  key: "/object_types/t/description",
  element_kind: "object_type",
  element_id: "t",
  element_label: "供应商",
  path: "description",
  kind: "field",
  base: "基线",
  latest: "最新",
  draft: "草稿",
  allowed: ["latest", "draft", "custom"],
};

const renderPanel = (props: Partial<Parameters<typeof PublishPanel>[0]> = {}) =>
  render(
    <PublishPanel
      session={session}
      onSession={vi.fn()}
      onPublished={vi.fn()}
      onStale={vi.fn()}
      {...props}
    />,
    { wrapper: MemoryRouter },
  );

/** Open the confirm dialog from the top-right button and confirm. */
async function publishFromHeader(version: number, note = "") {
  fireEvent.click(await screen.findByRole("button", { name: `发布 v${version}` }));
  const dialog = await screen.findByRole("dialog", { name: `发布 v${version}` });
  if (note) fireEvent.change(within(dialog).getByPlaceholderText("说明本次模型变化"), { target: { value: note } });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认发布" }));
  return dialog;
}

describe("publish panel", () => {
  it("shows what publishing changes and publishes with exactly the previewed values", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview());
    const publish = vi.spyOn(publishApi, "publish").mockResolvedValue({
      version: { version: 3 } as never,
      session,
    });
    const onPublished = vi.fn();
    renderPanel({ onPublished });
    await screen.findByRole("button", { name: "发布 v3" });
    expect(screen.getByText("v2", { selector: "b" })).toBeInTheDocument();
    expect(screen.getByText("可发布")).toBeInTheDocument();
    expect(screen.getByLabelText("变更计数")).toHaveTextContent("+1~1−0");
    expect(screen.getByText("会话开始于 v1，之后发布的 v2 已纳入合并")).toBeInTheDocument();
    expect(screen.getByText("本次发布将改变的内容")).toBeInTheDocument();
    expect(screen.getByText("仅定义")).toBeInTheDocument();
    expect(screen.getByText(/会话开始后已发布的变化 1/)).toBeInTheDocument();
    expect(screen.queryByText(/草稿/)).not.toBeInTheDocument();
    const card = screen.getByRole("article", { name: "实体 供应商" });
    expect(within(card).getByText("新定义")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "JSON" }));
    expect(within(card).getByText("发布后")).toBeInTheDocument();

    const dialog = await publishFromHeader(3, "上线");
    expect(dialog).toHaveTextContent("当前发布版本 v2 → 新版本 v3");
    await waitFor(() => expect(onPublished).toHaveBeenCalled());
    expect(publish).toHaveBeenCalledWith(session, preview(), "上线");
  });

  it("drops an outdated preview and previews again", async () => {
    const previewCall = vi
      .spyOn(publishApi, "preview")
      .mockResolvedValueOnce(preview())
      .mockResolvedValue(preview({ next_version_number: 4, current_version_number: 3 }));
    vi.spyOn(publishApi, "publish").mockRejectedValue(
      new ApiError("最新版本已变化", 409, "PREVIEW_OUTDATED"),
    );
    const onStale = vi.fn();
    renderPanel({ onStale });
    await publishFromHeader(3);
    await screen.findByRole("button", { name: "发布 v4" });
    expect(previewCall).toHaveBeenCalledTimes(2);
    expect(onStale).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("预览后已变化");
  });

  it("blocks publishing while validation fails and shows why in the checks tab", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(
      preview({
        validation: {
          ...preview().validation,
          publishable: false,
          errors: [{ message: "名称重复" }],
        },
      }),
    );
    renderPanel();
    expect(await screen.findByRole("button", { name: "发布 v3" })).toBeDisabled();
    expect(screen.getByText("校验未通过 · 1 个错误")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /检查/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("名称重复");
  });

  it("follows the server's publishable verdict even without listed errors", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(
      preview({ validation: { ...preview().validation, publishable: false } }),
    );
    renderPanel();
    expect(await screen.findByRole("button", { name: "发布 v3" })).toBeDisabled();
    expect(screen.getAllByText("校验未通过").length).toBeGreaterThan(0);
  });

  it("does not offer to publish a version without changes", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview({ changes: [], auto_merged: [] }));
    renderPanel();
    expect(await screen.findByRole("button", { name: "发布 v3" })).toBeDisabled();
    expect(screen.getByText("本会话不会改变当前发布版本。")).toBeInTheDocument();
  });

  it("publishes a change to workspace constraints alone", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(
      preview({ changes: [], auto_merged: [], requires_change: { before: ["旧约束"], after: ["新约束"] } }),
    );
    renderPanel();
    expect(await screen.findByRole("button", { name: "发布 v3" })).toBeEnabled();
    const card = screen.getByRole("article", { name: "空间 工作空间约束" });
    expect(within(card).getByText("新约束")).toBeInTheDocument();
    expect(within(card).getByText("旧约束")).toBeInTheDocument();
    expect(screen.getByLabelText("变更计数")).toHaveTextContent("+0~1−0");
  });

  it("does not show checks as passed when the preview failed", async () => {
    vi.spyOn(publishApi, "preview").mockRejectedValue(new Error("网络错误"));
    renderPanel();
    await screen.findByText(/网络错误/);
    fireEvent.click(screen.getByRole("tab", { name: /检查/ }));
    const checks = screen.getByRole("tabpanel", { name: /检查/ });
    expect(within(checks).getAllByText("等待预览").length).toBe(2);
    expect(checks.querySelector(".check-pass")).toBeNull();
  });

  it("starts a long list collapsed", async () => {
    const many = Array.from({ length: 21 }, (_, i) => ({
      ...preview().changes[0],
      element_id: "t" + i,
      label: "实体" + i,
    }));
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview({ changes: many }));
    renderPanel();
    expect(await screen.findByRole("button", { name: "展开 实体0" })).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: "全部展开" }));
    expect(screen.getByRole("button", { name: "收起 实体0" })).toHaveAttribute("aria-expanded", "true");
  });

  it("switches tabs with the arrow keys", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview());
    renderPanel();
    await screen.findByRole("button", { name: "发布 v3" });
    fireEvent.keyDown(screen.getByRole("tab", { name: /变更/ }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /检查/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /检查/ })).toHaveFocus();
  });

  it("resolves conflicts one at a time and saves them together", async () => {
    vi.spyOn(publishApi, "preview").mockRejectedValue(
      new ApiError("冲突", 409, "MERGE_CONFLICTS", undefined, {
        conflicts: [conflict, { ...conflict, key: "/object_types/t/tags", path: "tags", allowed: ["latest", "draft", "custom", "both"] }],
        current_version_id: "v2",
      }),
    );
    const resolve = vi.spyOn(publishApi, "resolve").mockResolvedValue({ ...session, revision: 5 });
    const onSession = vi.fn();
    renderPanel({ onSession });
    await screen.findByLabelText("解决冲突");
    const save = screen.getByRole("button", { name: "应用到会话并重新预览" });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /自定义/ }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "合并后" } });
    fireEvent.click(screen.getByRole("button", { name: "下一个" }));
    fireEvent.click(screen.getByRole("radio", { name: /都保留/ }));
    expect(screen.getByText("已解决 2 / 2")).toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(onSession).toHaveBeenCalledWith({ ...session, revision: 5 }));
    expect(resolve).toHaveBeenCalledWith(session, "v2", {
      "/object_types/t/description": { choice: "custom", value: "合并后" },
      "/object_types/t/tags": { choice: "both" },
    });
  });

  it("re-merges when the version moved while resolving", async () => {
    const previewCall = vi
      .spyOn(publishApi, "preview")
      .mockRejectedValueOnce(
        new ApiError("冲突", 409, "MERGE_CONFLICTS", undefined, {
          conflicts: [conflict],
          current_version_id: "v2",
        }),
      )
      .mockResolvedValue(preview({ next_version_number: 4 }));
    vi.spyOn(publishApi, "resolve").mockRejectedValue(
      new ApiError("又变了", 409, "PREVIEW_OUTDATED"),
    );
    const onStale = vi.fn();
    renderPanel({ onStale });
    await screen.findByLabelText("解决冲突");
    fireEvent.click(screen.getByRole("radio", { name: /采用本会话修改/ }));
    fireEvent.click(screen.getByRole("button", { name: "应用到会话并重新预览" }));
    await screen.findByRole("button", { name: "发布 v4" });
    expect(previewCall).toHaveBeenCalledTimes(2);
    expect(onStale).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("预览后已变化");
  });

  it("ignores a late preview for an earlier revision", async () => {
    let late!: (value: PublishPreview) => void;
    vi.spyOn(publishApi, "preview")
      .mockImplementationOnce(() => new Promise((resolve) => (late = resolve)))
      .mockResolvedValue(preview({ next_version_number: 9 }));
    const view = renderPanel();
    view.rerender(
      <PublishPanel session={{ ...session, revision: 5 }} onSession={vi.fn()} onPublished={vi.fn()} onStale={vi.fn()} />,
    );
    await screen.findByRole("button", { name: "发布 v9" });
    await act(async () => late(preview()));
    expect(screen.queryByRole("button", { name: "发布 v3" })).not.toBeInTheDocument();
  });
});

describe("line diff", () => {
  it("marks reordered lines instead of hiding them", () => {
    const { removed, added } = lineDiff(["[", '"a",', '"b"', "]"], ["[", '"b",', '"a"', "]"]);
    expect(removed.some(Boolean) && added.some(Boolean)).toBe(true);
    expect(removed[0] || removed[3] || added[0] || added[3]).toBe(false);
  });

  it("counts a repeated line once per occurrence", () => {
    expect(lineDiff(["x", "x"], ["x"])).toEqual({ removed: [false, true], added: [false] });
  });
});
