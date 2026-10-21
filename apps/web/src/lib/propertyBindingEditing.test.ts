import { describe, expect, it } from "vitest";
import { example } from "../test/drafts";
import { preservePropertyBindings, type PropertyBindingEdits } from "./propertyBindingEditing";

describe("shared parent property bindings", () => {
  it("keeps ancestor bindings through a rename and a subsequent column edit", () => {
    const before = example("06-inheritance");
    const vip = before.object_types.find((o) => o.name === "vip_party")!;
    const note = before.properties.find((p) => p.owner_type_id === vip.id)!;
    const mapping = before.mappings.find((m) => m.type_id === vip.id)!;
    expect(mapping.sources).toEqual([]);
    const edits: PropertyBindingEdits = new Map();
    const renamed = preservePropertyBindings(before, {
      ...before,
      properties: before.properties.map((p) => p.id === note.id ? { ...p, name: "note2" } : p),
    }, edits);
    expect(renamed.mappings.find((m) => m.id === mapping.id)!.fields).toEqual({ note2: mapping.fields.note });
    const rebound = preservePropertyBindings(renamed, {
      ...renamed,
      mappings: renamed.mappings.map((m) => m.id === mapping.id ? {
        ...m, fields: { note2: { kind: "column", source_id: "main", column: "party_name" } },
      } : m),
    }, edits);
    expect(rebound.mappings.find((m) => m.id === mapping.id)!.fields).toEqual({
      note2: { kind: "column", source_id: "main", column: "party_name" },
    });
    expect(before.mappings.find((m) => m.id === mapping.id)!.fields).toEqual({
      note: { kind: "column", source_id: "main", column: "vip_note" },
    });
  });

  it("removes a binding when its ancestor source is removed in the next graph", () => {
    const before = example("06-inheritance");
    const vip = before.object_types.find((o) => o.name === "vip_party")!;
    const next = structuredClone(before);
    next.properties.find((p) => p.owner_type_id === vip.id)!.name = "note2";
    next.mappings = next.mappings.filter((m) => m.type_id === vip.id);
    const result = preservePropertyBindings(before, next, new Map());
    expect(result.mappings[0].fields).toEqual({});
  });
});
