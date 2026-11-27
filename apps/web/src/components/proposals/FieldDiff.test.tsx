import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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

    expect(screen.getByText(/班组代码 \(team_code\)：文本 \/ 值类型「班组编码」（必填） — 受理班组/)).toBeInTheDocument();
    expect(screen.getByText(/修改属性：状态 — 置为已派单/)).toBeInTheDocument();
    expect(screen.getByText(/建立关系：受理班组关系 — 关联班组/)).toBeInTheDocument();
    expect(screen.queryByLabelText("修改参数")).toBeNull();
    expect(screen.queryByLabelText("修改效果")).toBeNull();
  });
});
