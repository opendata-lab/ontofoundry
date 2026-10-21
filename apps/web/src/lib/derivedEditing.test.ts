import { describe, expect, it } from "vitest";
import type { DerivedBranch } from "../api/types";
import { example } from "../test/drafts";
import { branchProblem, branchesFromForm, formErrors, formFromBranches, newPropertyRow, type LinkRow } from "./derivedEditing";

const draft = example("06-inheritance");
const party = draft.object_types.find((o) => o.name === "party")!;
const vip = draft.object_types.find((o) => o.name === "vip_party")!;
const level = draft.properties.find((p) => p.name === "level" && p.owner_type_id === party.id)!;
const signer = draft.link_types.find((l) => (l.display_name || l.name) === "signer")!;
const contact = draft.link_types.find((l) => (l.display_name || l.name) === "contact")!;

describe("member condition form", () => {
  it("reads a single simple branch as rows and writes the same branch back", () => {
    const form = formFromBranches(draft, party.id, vip.derived_by);
    expect(form.mode).toBe("simple");
    expect(branchesFromForm(draft, party.id, form)).toEqual(vip.derived_by);
  });
  it("saves relation rows as one EXISTS expression and reads it back as rows", () => {
    const rows = [
      { ...newPropertyRow(level), operator: "eq" as const, values: ["VIP"] },
      { key: "l1", kind: "link", linkId: signer.id, direction: "reverse", has: true } satisfies LinkRow,
      { key: "l2", kind: "link", linkId: contact.id, direction: "forward", has: false } satisfies LinkRow,
    ];
    const branches = branchesFromForm(draft, party.id, { mode: "simple", rows });
    expect(branches).toEqual([
      { kind: "expression", expression: "party.level = 'VIP' AND EXISTS (party.REVERSE(signer)) AND NOT EXISTS (party.contact)" },
    ]);
    const back = formFromBranches(draft, party.id, branches);
    expect(back.mode).toBe("simple");
    expect(back.mode === "simple" && back.rows.map((r) => (r.kind === "link" ? [r.linkId, r.direction, r.has] : r.values))).toEqual([
      ["VIP"],
      [signer.id, "reverse", true],
      [contact.id, "forward", false],
    ]);
  });
  it("shows several branches or unparsed text as one expression joined by OR", () => {
    const branches: DerivedBranch[] = [
      ...vip.derived_by,
      { kind: "expression", expression: "party.phone LIKE '138%'" },
    ];
    expect(formFromBranches(draft, party.id, branches)).toEqual({
      mode: "expression",
      expression: "(party.level = 'VIP') OR (party.phone LIKE '138%')",
    });
  });
  it("keeps BETWEEN and IN values when parsing", () => {
    const branches: DerivedBranch[] = [
      { kind: "expression", expression: "party.level IN ('VIP', 'SVIP') AND party.name BETWEEN 'a' AND 'm' AND EXISTS (party.contact)" },
    ];
    const form = formFromBranches(draft, party.id, branches);
    expect(form.mode === "simple" && form.rows.map((r) => (r.kind === "property" ? [r.operator, r.values] : r.kind))).toEqual([
      ["in", ["VIP", "SVIP"]],
      ["between", ["a", "m"]],
      "link",
    ]);
  });
  it("reports incomplete rows, not_in empty values and non-numeric values before saving", () => {
    const row = { ...newPropertyRow(level), operator: "between" as const, values: ["a"] };
    expect(formErrors(draft, { mode: "simple", rows: [row] })[row.key]).toBe("请填写起止两个值");
    expect(branchProblem(draft, branchesFromForm(draft, party.id, { mode: "simple", rows: [row] }))).toContain("第 1 个条件");
    expect(branchesFromForm(draft, party.id, { mode: "simple", rows: [] })).toEqual([]);

    const notInNull = { ...newPropertyRow(level), operator: "not_in" as const, values: ["VIP", null] };
    expect(formErrors(draft, { mode: "simple", rows: [notInNull] })[notInNull.key]).toBe("“不属于”的值不能包含空值");

    const sales = example("01-basic-sales");
    const order = sales.object_types.find((o) => o.name === "sales_order")!;
    const amount = sales.properties.find((p) => p.owner_type_id === order.id && p.name === "amount")!;
    const badNum = { ...newPropertyRow(amount), operator: "gt" as const, values: ["abc"] };
    expect(formErrors(sales, { mode: "simple", rows: [badNum] })[badNum.key]).toBe("数值属性的条件值必须是数字");
  });
  it("stores boolean in and not_in values as booleans", () => {
    const inst = example("07-instances-and-evidence");
    const customer = inst.object_types.find((o) => o.name === "customer")!;
    const isVip = inst.properties.find((p) => p.owner_type_id === customer.id && p.name === "is_vip")!;
    const row = { ...newPropertyRow(isVip), operator: "in" as const, values: ["true", "false"] };
    const branches = branchesFromForm(inst, customer.id, { mode: "simple", rows: [row] });
    expect(branches).toEqual([
      {
        kind: "simple",
        conditions: [{ path: { links: [], property_id: isVip.id }, operator: "in", values: [true, false] }],
      },
    ]);
  });
});
