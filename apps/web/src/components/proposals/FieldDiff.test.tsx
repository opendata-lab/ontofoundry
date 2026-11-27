import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buildQualifiedReferenceNames } from "../../lib/actionFormat";
import { renderWithProviders } from "../../test/renderWithProviders";
import { FieldDiff } from "./FieldDiff";

afterEach(cleanup);

const changes = [
  { path: "display_name", before: null, after: "退款数据" },
  { path: "owner_type_id", before: null, after: "11111111-1111-4111-8111-111111111111" },
  { path: "multiplicity", before: "many_to_one", after: "one_to_one" },
];

describe("FieldDiff inline editing", () => {
  it("edits a proposed value in place and saves it on Enter", async () => {
    const onEdit = vi.fn().mockResolvedValue(true);
    renderWithProviders(<FieldDiff changes={changes} onEdit={onEdit} />);

    expect(screen.queryByLabelText("修改所属")).toBeNull();
    fireEvent.click(screen.getByLabelText("修改名称"));
    const input = screen.getByLabelText("名称");
    fireEvent.change(input, { target: { value: "退款明细" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(onEdit).toHaveBeenCalledWith("display_name", "退款明细"));
    await waitFor(() => expect(screen.queryByLabelText("保存名称")).toBeNull());
  });

  it("parses JSON typed into an empty structured field", async () => {
    const onEdit = vi.fn().mockResolvedValue(true);
    renderWithProviders(<FieldDiff changes={[{ path: "columns", before: null, after: null }]} onEdit={onEdit} />);
    fireEvent.click(screen.getByLabelText("修改列"));
    const input = screen.getByLabelText("列");
    fireEvent.change(input, { target: { value: '[{"name":"id"}]' } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(onEdit).toHaveBeenCalledWith("columns", [{ name: "id" }]));
  });

  it("cancels with Escape and keeps the editor open when the server refuses", async () => {
    const onEdit = vi.fn().mockResolvedValue(false);
    renderWithProviders(<FieldDiff changes={changes} onEdit={onEdit} />);

    fireEvent.click(screen.getByLabelText("修改名称"));
    fireEvent.keyDown(screen.getByLabelText("名称"), { key: "Escape" });
    expect(screen.queryByLabelText("保存名称")).toBeNull();

    fireEvent.click(screen.getByLabelText("修改名称"));
    fireEvent.click(screen.getByLabelText("保存名称"));
    await waitFor(() => expect(screen.getByText("保存未通过，请按提示修改")).toBeTruthy());
  });

  it("is read-only without an edit handler", () => {
    renderWithProviders(<FieldDiff changes={changes} />);
    expect(screen.queryByLabelText("修改名称")).toBeNull();
  });

  it("renders action parameters and effects with resolved names and locks them against inline editing", () => {
    const onEdit = vi.fn().mockResolvedValue(true);
    const names = new Map([
      ["vt-1", "班组编码"],
      ["prop-1", "状态"],
      ["link-1", "受理班组关系"],
    ]);
    renderWithProviders(
      <FieldDiff
        names={names}
        onEdit={onEdit}
        changes={[
          {
            path: "parameters",
            before: [],
            after: [{ name: "team_code", display_name: "班组代码", value_kind: "string", value_type_id: "vt-1", required: true, description: "受理班组" }],
          },
          {
            path: "effects",
            before: [],
            after: [
              { kind: "set_property", property_id: "prop-1", description: "置为已派单" },
              { kind: "add_link", link_type_id: "link-1", description: "关联班组" },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByText(/班组代码 \(team_code\)：文本 \/ 值类型「/)).toBeInTheDocument();
    expect(screen.getByText("班组编码")).toBeInTheDocument();
    expect(screen.getByText("状态")).toBeInTheDocument();
    expect(screen.getByText("受理班组关系")).toBeInTheDocument();
    expect(screen.queryByLabelText("修改参数")).toBeNull();
    expect(screen.queryByLabelText("修改效果")).toBeNull();
  });

  it("distinguishes rebinding between same-named properties using qualified names and preserves UUID hints", async () => {
    const names = buildQualifiedReferenceNames(
      [
        {
          object_types: [
            { id: "obj-wo", name: "work_order", display_name: "工单" },
            { id: "obj-team", name: "maintenance_team", display_name: "受理班组" },
          ],
          properties: [
            { id: "prop-wo-status", owner_type_id: "obj-wo", name: "status", display_name: "状态" },
            { id: "prop-team-status", owner_type_id: "obj-team", name: "status", display_name: "状态" },
          ],
          link_types: [
            { id: "link-handled", name: "handled_by", display_name: "受理班组关系", source_type_id: "obj-wo", target_type_id: "obj-team" },
          ],
        },
      ],
      new Map(),
    );
    renderWithProviders(
      <FieldDiff
        beforeNames={names}
        names={names}
        changes={[
          {
            path: "effects",
            before: [{ kind: "set_property", property_id: "prop-wo-status", description: "更新状态" }],
            after: [
              { kind: "set_property", property_id: "prop-team-status", description: "更新状态" },
              { kind: "add_link", link_type_id: "link-handled", description: "建立关联" },
            ],
          },
        ]}
      />,
    );

    expect(screen.getByText("工单.状态")).toBeInTheDocument();
    expect(screen.getByText("受理班组.状态")).toBeInTheDocument();
    expect(screen.getByText("受理班组关系（工单 → 受理班组）")).toBeInTheDocument();
    fireEvent.mouseOver(screen.getByText("受理班组.状态"));
    expect(await screen.findByText("prop-team-status")).toBeInTheDocument();
  });
});
