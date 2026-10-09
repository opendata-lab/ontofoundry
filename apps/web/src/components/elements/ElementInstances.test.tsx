import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LegacyDraft } from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { ElementInstances } from "./ElementInstances";

const model = (reverse = false): LegacyDraft => ({
  ...emptyDraft("w"),
  object_types: [
    { id: "return", name: "退货单", technical_name: "sales_return", description: "", tags: [], extends: [], evidence: [] },
    { id: "order", name: "订单", technical_name: "order", description: "", tags: [], extends: [], evidence: [] },
  ],
  link_types: [{ id: "relation", name: "针对订单", technical_name: "targets_order", description: "", tags: [], evidence: [],
    source_type_id: reverse ? "order" : "return", target_type_id: reverse ? "return" : "order", multiplicity: "many_to_one",
    owner_ref: { kind: "object_type", ref: "return" }, owner_role_id: "owner",
    roles: [{ id: "other", concept: { kind: "object_type", ref: "order" } }], endpoint_direction: reverse ? "reverse" : "forward" }],
  material_objects: [
    { id: "a", type_id: "return", name: "RT-202601-001", values: {}, evidence: [] },
    { id: "b", type_id: "order", name: "订单编号 1", values: {}, evidence: [] },
  ],
  material_links: [{ id: "fact", type_id: "relation", source_id: null, target_id: null, evidence: [],
    role_values: [{ role_id: "other", object_id: "b" }, { role_id: "owner", object_id: "a" }] }],
});
const common = { editing: false, change: vi.fn(), open: vi.fn(), sessionId: null, canBrowseDatabase: false };
afterEach(cleanup);
describe("仅角色值的二元实例", () => {
  it.each([false, true])("shows both instance names in the relation panel (reverse=%s)", reverse => {
    const draft = model(reverse);
    render(<ElementInstances {...common} draft={draft} type={draft.link_types[0]} />);
    const row = within(screen.getByRole("table")).getAllByRole("row")[1];
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent(reverse ? "订单编号 1" : "RT-202601-001");
    expect(cells[1]).toHaveTextContent(reverse ? "RT-202601-001" : "订单编号 1");
    expect(draft.material_links[0].source_id).toBeNull();
  });
  it("visits a role-only relation from a selected document object", () => {
    const draft = model();
    render(<ElementInstances {...common} draft={draft} type={draft.object_types[0]} initialObjectId="a" />);
    fireEvent.click(screen.getByRole("button", { name: /针对订单.*订单编号 1/ }));
    expect(screen.getByRole("heading", { name: "订单编号 1" })).toBeInTheDocument();
  });
});
