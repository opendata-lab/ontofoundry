import { describe, expect, it } from "vitest";
import type { Draft } from "../api/types";
import { emptyDraft, fromView, toView } from "./draftView";

const evidence = [
  {
    kind: "material" as const,
    id: "e1",
    material_id: "m1",
    material_sha256: null,
    locator: { line_start: 1, line_end: 2 },
    quote: "原文",
  },
];

function draft(): Draft {
  return {
    ...emptyDraft("w"),
    ontology_requires: ["EXISTS (supplier)"],
    object_types: [
      {
        id: "t1",
        name: "供应商",
        technical_name: "supplier",
        description: "",
        tags: [],
        extends: [],
        evidence,
      },
    ],
    properties: [
      {
        id: "p1",
        owner_type_id: "t1",
        name: "编码",
        technical_name: "code",
        description: "",
        value_kind: "string",
        required: true,
        identifier: true,
        verbalizes: [],
        evidence: [],
      },
    ],
    rules: [
      {
        id: "r1",
        name: "编码必填",
        technical_name: "code_required",
        description: "",
        owner_kind: "property",
        owner_id: "p1",
        rule_kind: "constraint",
        expression: "supplier.code IS NOT NULL",
        verbalizes: [],
        evidence: [],
      },
      {
        id: "r2",
        name: "只审批一次",
        technical_name: "approve_once",
        description: "",
        owner_kind: "action",
        owner_id: "a1",
        rule_kind: "constraint",
        expression: "approved = FALSE",
        verbalizes: [],
        evidence: [],
      },
    ],
  };
}

describe("draftView", () => {
  it("presents properties and rules on their owners", () => {
    const view = toView(draft());
    expect(view.requires).toEqual(["EXISTS (supplier)"]);
    const [type] = view.object_types;
    expect(type.attributes.map((a) => a.technical_name)).toEqual(["code"]);
    expect(type.attributes[0].requires).toEqual(["supplier.code IS NOT NULL"]);
  });

  it("round-trips unchanged without touching ids or evidence", () => {
    const original = draft();
    expect(fromView(original, toView(original))).toEqual(original);
  });

  it("keeps a rule's id when its expression is edited", () => {
    const original = draft();
    const view = toView(original);
    view.object_types[0].attributes[0].requires = ["LENGTH(supplier.code) = 8"];
    const next = fromView(original, view);
    const rule = next.rules.find((r) => r.owner_id === "p1");
    expect(rule?.id).toBe("r1");
    expect(rule?.expression).toBe("LENGTH(supplier.code) = 8");
    expect(rule?.technical_name).toBe("code_required");
  });

  it("mints ids only for real additions and keeps action rules", () => {
    const original = draft();
    const view = toView(original);
    view.object_types[0].attributes[0].requires = [
      "supplier.code IS NOT NULL",
      "LENGTH(supplier.code) = 8",
      "LENGTH(supplier.code) = 8",
    ];
    const next = fromView(original, view);
    const propertyRules = next.rules.filter((r) => r.owner_id === "p1");
    expect(propertyRules).toHaveLength(2);
    expect(propertyRules[0].id).toBe("r1");
    expect(propertyRules[1].id).not.toBe("r1");
    expect(propertyRules[1].technical_name).toMatch(/^constraint_[0-9a-f]{8}$/);
    // Action-owned rules are outside the view and survive untouched, so an
    // action precondition pointing at r2 stays valid.
    expect(next.rules.find((r) => r.id === "r2")).toEqual(original.rules[1]);
  });

  it("keeps ids when one of several expressions is edited", () => {
    const original = draft();
    original.rules.splice(1, 0, {
      ...original.rules[0],
      id: "r3",
      technical_name: "second",
      expression: "supplier.code <> ''",
    });
    const view = toView(original);
    view.object_types[0].attributes[0].requires = [
      "supplier.code IS NOT NULL",
      "supplier.code <> 'x'",
    ];
    const ids = fromView(original, view)
      .rules.filter((r) => r.owner_id === "p1")
      .map((r) => r.id);
    expect(ids).toEqual(["r1", "r3"]);
  });

  it("drops rules whose expressions were removed", () => {
    const original = draft();
    const view = toView(original);
    view.object_types[0].attributes[0].requires = [];
    expect(fromView(original, view).rules.map((r) => r.id)).toEqual(["r2"]);
  });

  it("gives new properties their owner and keeps existing evidence", () => {
    const original = draft();
    const view = toView(original);
    view.object_types[0].attributes.push({
      id: "p2",
      name: "名称",
      technical_name: "name",
      description: "",
      value_kind: "string",
      required: false,
      identifier: false,
    });
    const next = fromView(original, view);
    expect(next.properties.find((p) => p.id === "p2")?.owner_type_id).toBe("t1");
    expect(next.object_types[0].evidence).toEqual(evidence);
  });
});
