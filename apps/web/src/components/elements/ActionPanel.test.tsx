import { cleanup, fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Draft } from "../../api/types";
import { emptyDraft } from "../../lib/coreModel";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ActionReadOnlyPanel, ObjectActionsPanel } from "./ActionPanel";

afterEach(cleanup);

function workOrderDraft(): Draft {
  return {
    ...emptyDraft("ws-ops"),
    value_types: [
      { id: "vt-team", name: "team_code", display_name: "班组编码", value_kind: "string", description: "", evidence: [] },
    ],
    object_types: [
      { id: "obj-wo", name: "work_order", display_name: "工单", description: "运维工单", synonyms: [], tags: [], extends: null, title_property_id: null, derived_by: [], evidence: [] },
      { id: "obj-insp", name: "inspection_order", display_name: "巡检工单", description: "定期巡检工单", synonyms: [], tags: [], extends: "obj-wo", title_property_id: null, derived_by: [], evidence: [] },
      { id: "obj-team", name: "maintenance_team", display_name: "受理班组", description: "", synonyms: [], tags: [], extends: null, title_property_id: null, derived_by: [], evidence: [] },
    ],
    properties: [
      { id: "prop-status", owner_type_id: "obj-wo", name: "status", display_name: "状态", description: "", value_kind: "string", value_type_id: null, required: true, identifier: false, unique: false, synonyms: [], evidence: [] },
    ],
    link_types: [
      { id: "link-team", name: "handled_by", display_name: "受理班组关系", description: "", synonyms: [], tags: [], verbalizes: [], source_type_id: "obj-wo", target_type_id: "obj-team", multiplicity: "many_to_one", source_role_name: null, target_role_name: null, data_join: null, evidence: [] },
    ],
    actions: [
      {
        id: "act-dispatch",
        name: "dispatch_work_order",
        display_name: "派单",
        description: "只有待派单工单可以派单，必须指定受理班组。",
        synonyms: ["分派工单"],
        tags: ["工单流转"],
        target_type_id: "obj-wo",
        parameters: [
          { name: "team_code", display_name: "受理班组编码", value_kind: "string", value_type_id: "vt-team", required: true, description: "目标班组" },
        ],
        effects: [
          { kind: "set_property", property_id: "prop-status", description: "状态变为已派单" },
          { kind: "add_link", link_type_id: "link-team", description: "关联受理班组" },
        ],
        evidence: [],
      },
      {
        id: "act-create-insp",
        name: "create_inspection_order",
        display_name: "创建巡检工单",
        description: "由调度员新建巡检工单。",
        synonyms: [],
        tags: ["工单创建"],
        target_type_id: null,
        parameters: [],
        effects: [
          { kind: "create_object", object_type_id: "obj-insp", description: "生成巡检工单" },
        ],
        evidence: [],
      },
    ],
  };
}

describe("ActionPanel", () => {
  it("lists inherited actions on a child object type with 仅定义 tag and navigable references", () => {
    const draft = workOrderDraft();
    const open = vi.fn();
    const inspection = draft.object_types.find((o) => o.id === "obj-insp")!;

    renderWithProviders(
      <MemoryRouter>
        <ObjectActionsPanel draft={draft} type={inspection} open={open} />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("派单").length).toBeGreaterThan(0);
    expect(screen.getAllByText("仅定义").length).toBeGreaterThan(0);
    expect(screen.getByText("继承自 工单")).toBeInTheDocument();
    expect(screen.getByText("受理班组编码")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "值类型 班组编码" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "工单.状态" }));
    expect(open).toHaveBeenCalledWith({ kind: "property", id: "prop-status" });

    fireEvent.click(screen.getByRole("button", { name: "打开动作详情" }));
    expect(open).toHaveBeenCalledWith({ kind: "action", id: "act-dispatch" });
  });

  it("renders a standalone global action read-only with 全局动作 tag and clickable effect target", () => {
    const draft = workOrderDraft();
    const open = vi.fn();
    const globalAction = draft.actions.find((a) => a.id === "act-create-insp")!;

    renderWithProviders(
      <MemoryRouter>
        <ActionReadOnlyPanel draft={draft} action={globalAction} open={open} />
      </MemoryRouter>,
    );

    expect(screen.getByText("全局动作")).toBeInTheDocument();
    expect(screen.getByText("create_inspection_order")).toBeInTheDocument();
    expect(screen.getByText("无参数")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "巡检工单" }));
    expect(open).toHaveBeenCalledWith({ kind: "object_type", id: "obj-insp" });
  });
});
