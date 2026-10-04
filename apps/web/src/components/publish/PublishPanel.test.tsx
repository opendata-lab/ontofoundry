import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, publishApi } from "../../api/client";
import type { MergeConflict, ModelingSession, PublishPreview } from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { PublishPanel } from "./PublishPanel";

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
  );

/** Open the confirm dialog from the top-right button and confirm. */
async function publishFromHeader(version: number, note = "") {
  fireEvent.click(await screen.findByRole("button", { name: `发布为 v${version}` }));
  const dialog = await screen.findByRole("dialog", { name: `发布为 v${version}` });
  if (note) fireEvent.change(within(dialog).getByPlaceholderText("说明本次模型变化"), { target: { value: note } });
  fireEvent.click(within(dialog).getByRole("button", { name: "确认发布" }));
}

describe("publish panel", () => {
  it("shows the changes as cards and publishes with exactly the previewed values", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview());
    const publish = vi.spyOn(publishApi, "publish").mockResolvedValue({
      version: { version: 3 } as never,
      session,
    });
    const onPublished = vi.fn();
    renderPanel({ onPublished });
    await screen.findByRole("button", { name: "发布为 v3" });
    expect(screen.getByText("可发布")).toBeInTheDocument();
    expect(screen.getByLabelText("变更计数")).toHaveTextContent("+1~1−0");
    expect(screen.getByText("仅定义")).toBeInTheDocument();
    expect(screen.getByText(/来自其他会话的变更 1/)).toBeInTheDocument();
    // Cards open on the object view; the header toggles to JSON.
    const card = screen.getByRole("article", { name: "实体 供应商" });
    expect(within(card).getByText("新定义")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "JSON" }));
    expect(within(card).getByText("发布后")).toBeInTheDocument();

    await publishFromHeader(3, "上线");
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
    await screen.findByRole("button", { name: "发布为 v4" });
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
    expect(await screen.findByRole("button", { name: "发布为 v3" })).toBeDisabled();
    expect(screen.getByText("校验未通过 · 1 个错误")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /检查/ }));
    expect(screen.getByRole("alert")).toHaveTextContent("名称重复");
  });

  it("does not offer to publish a version without changes", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview({ changes: [], auto_merged: [] }));
    renderPanel();
    expect(await screen.findByRole("button", { name: "发布为 v3" })).toBeDisabled();
    expect(screen.getByText("草稿与最新版本一致，没有可发布的变更。")).toBeInTheDocument();
  });

  it("waits for unsaved workspace constraints", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview());
    renderPanel({ blockedReason: "工作空间约束尚未保存", disabled: true });
    expect(await screen.findByRole("button", { name: "发布为 v3" })).toBeDisabled();
    expect(screen.getByText("工作空间约束尚未保存")).toBeInTheDocument();
  });

  it("keeps the constraints box mounted while the checks tab is open", async () => {
    vi.spyOn(publishApi, "preview").mockResolvedValue(preview());
    renderPanel({ constraints: <textarea aria-label="约束草稿" defaultValue="未保存的约束" /> });
    await screen.findByRole("button", { name: "发布为 v3" });
    fireEvent.click(screen.getByRole("tab", { name: /检查/ }));
    fireEvent.click(screen.getByRole("tab", { name: /变更/ }));
    expect(screen.getByLabelText("约束草稿")).toHaveValue("未保存的约束");
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
    const save = screen.getByRole("button", { name: "保存并重新预览" });
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
    fireEvent.click(screen.getByRole("radio", { name: /采用我的草稿/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存并重新预览" }));
    await screen.findByRole("button", { name: "发布为 v4" });
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
    await screen.findByRole("button", { name: "发布为 v9" });
    await act(async () => late(preview()));
    expect(screen.queryByRole("button", { name: "发布为 v3" })).not.toBeInTheDocument();
  });
});
