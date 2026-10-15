import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LegacyDraft } from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { ElementInstances } from "./ElementInstances";

const model = (reverse = false): LegacyDraft => ({
  ...emptyDraft("w"),
  object_types: [
    {
      id: "return",
      name: "退货单",
      technical_name: "sales_return",
      description: "",
      tags: [],
      extends: [],
      evidence: [],
    },
    {
      id: "order",
      name: "订单",
      technical_name: "order",
      description: "",
      tags: [],
      extends: [],
      evidence: [],
    },
  ],
  link_types: [
    {
      id: "relation",
      name: "针对订单",
      technical_name: "targets_order",
      description: "",
      tags: [],
      evidence: [],
      source_type_id: reverse ? "order" : "return",
      target_type_id: reverse ? "return" : "order",
      multiplicity: "many_to_one",
      owner_ref: { kind: "object_type", ref: "return" },
      owner_role_id: "owner",
      roles: [{ id: "other", concept: { kind: "object_type", ref: "order" } }],
      endpoint_direction: reverse ? "reverse" : "forward",
    },
  ],
  material_objects: [
    {
      id: "a",
      type_id: "return",
      name: "RT-202601-001",
      values: {},
      evidence: [],
    },
    { id: "b", type_id: "order", name: "订单编号 1", values: {}, evidence: [] },
  ],
  material_links: [
    {
      id: "fact",
      type_id: "relation",
      source_id: null,
      target_id: null,
      evidence: [],
      role_values: [
        { role_id: "other", object_id: "b" },
        { role_id: "owner", object_id: "a" },
      ],
    },
  ],
});
const common = {
  editing: false,
  change: vi.fn(),
  open: vi.fn(),
  sessionId: null,
  canBrowseDatabase: false,
};
afterEach(cleanup);
describe("仅角色值的二元实例", () => {
  it.each([false, true])(
    "shows both instance names in the relation panel (reverse=%s)",
    (reverse) => {
      const draft = model(reverse);
      render(
        <ElementInstances
          {...common}
          draft={draft}
          type={draft.link_types[0]}
        />,
      );
      const row = within(screen.getByRole("table")).getAllByRole("row")[1];
      const cells = within(row).getAllByRole("cell");
      expect(cells[0]).toHaveTextContent(
        reverse ? "订单编号 1" : "RT-202601-001",
      );
      expect(cells[1]).toHaveTextContent(
        reverse ? "RT-202601-001" : "订单编号 1",
      );
      expect(draft.material_links[0].source_id).toBeNull();
    },
  );
  it("visits a role-only relation from a selected document object", () => {
    const draft = model();
    render(
      <ElementInstances
        {...common}
        draft={draft}
        type={draft.object_types[0]}
        initialObjectId="a"
      />,
    );
    expect(screen.getByText("针对订单")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "订单 · 订单编号 1" }),
    );
    expect(
      screen.getByRole("heading", { name: "订单编号 1" }),
    ).toBeInTheDocument();
  });
});

describe("approved instance table and side panel", () => {
  it("puts the identifier first, pages document rows, and keeps the table visible beside details", () => {
    const draft = model();
    draft.properties = [
      {
        id: "code",
        owner_type_id: "return",
        name: "退货编号",
        technical_name: "code",
        value_kind: "string",
        identifier: true,
        required: true,
        evidence: [],
        description: "",
        verbalizes: [],
      },
    ];
    draft.material_objects = Array.from({ length: 8 }, (_, index) => ({
      id: `row-${index}`,
      type_id: "return",
      name: `退货 ${index}`,
      values: { code: `RT-${index}` },
      evidence: [],
    }));
    render(
      <ElementInstances
        {...common}
        draft={draft}
        type={draft.object_types[0]}
      />,
    );
    expect(screen.getAllByRole("columnheader")[0]).toHaveTextContent(
      "实例标识",
    );
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(
      7,
    );
    fireEvent.click(screen.getByRole("button", { name: "RT-0" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "实例详情" }),
    ).toHaveTextContent("退货编号RT-0");
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(
      screen.queryByRole("complementary", { name: "实例详情" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RT-6" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "搜索实例" }), {
      target: { value: "RT-7" },
    });
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(
      2,
    );
    expect(screen.getByRole("button", { name: "RT-7" })).toBeInTheDocument();
  });
});
