import { useState } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { LegacyDraft, NativeDraft } from "../../api/types";
import fixture from "../../lib/nativeDraft.fixture.json";
import { editorDraft, nativeFromEditor } from "../../lib/nativeDraft";
import { NativeRolesEditor } from "./NativeRolesEditor";

afterEach(cleanup);
function setup() {
  const native = structuredClone(fixture) as NativeDraft;
  const changed = vi.fn<(draft: LegacyDraft) => void>();
  function Editor() {
    const [draft, setDraft] = useState(() => editorDraft(native));
    return (
      <form>
        <NativeRolesEditor
          draft={draft}
          nativeDraft={native}
          type={draft.link_types[1]}
          editing
          open={vi.fn()}
          change={(next) => {
            setDraft(next);
            changed(next);
          }}
        />
      </form>
    );
  }
  render(<Editor />);
  return { native, changed };
}
it("adds, changes and deletes native roles without inferred names", () => {
  const { native, changed } = setup();
  fireEvent.click(screen.getByRole("button", { name: "添加角色" }));
  expect(screen.getByLabelText("角色 4 名称")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("角色 4 概念"), {
    target: { value: `value_type:${native.value_types[0].id}` },
  });
  const result = nativeFromEditor(
    native,
    changed.mock.calls.at(-1)![0],
  ) as NativeDraft;
  expect(result.link_types[1].roles[3].concept).toEqual({
    kind: "value_type",
    ref: native.value_types[0].id,
  });
  expect(result.link_types[1].roles[3].name).toBeNull();
  expect(result.link_types[1].roles[3].native_presence).not.toContain("name");
  fireEvent.click(screen.getByRole("button", { name: "删除角色 4" }));
  expect(changed.mock.calls.at(-1)![0].link_types[1].roles).toHaveLength(3);
});
it("updates explicit placeholders and reports unknown placeholders", () => {
  const { changed } = setup();
  fireEvent.change(screen.getByLabelText("角色 1 名称"), {
    target: { value: "shipment" },
  });
  expect(changed.mock.calls.at(-1)![0].link_types[1].verbalizes![0]).toContain(
    "{product:shipment}",
  );
  fireEvent.change(screen.getByLabelText("角色 1 名称"), {
    target: { value: "" },
  });
  expect(changed.mock.calls.at(-1)![0].link_types[1].verbalizes![0]).toContain(
    "{product}",
  );
  fireEvent.change(screen.getByLabelText("语义描述 1"), {
    target: { value: "{unknown_role} 无效" },
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "未知占位符：unknown_role",
  );
  expect(
    (
      screen.getByLabelText("语义描述 1") as HTMLTextAreaElement
    ).checkValidity(),
  ).toBe(false);
});

it("inserts a concept placeholder at the caret and restores text focus", async () => {
  setup();
  const input = screen.getByLabelText("语义描述 1") as HTMLTextAreaElement;
  fireEvent.change(input, { target: { value: "前后" } });
  input.setSelectionRange(1, 1);
  fireEvent.focus(input);
  fireEvent.click(
    within(input.closest(".native-description") as HTMLElement).getByRole(
      "button",
      { name: /^supplier$/ },
    ),
  );
  expect(input).toHaveValue("前{supplier}后");
  await waitFor(() => expect(input).toHaveFocus());
  expect(input.selectionStart).toBe(11);
});
