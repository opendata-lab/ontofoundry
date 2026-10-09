import { describe, expect, it } from "vitest";
import type { NativeDraft } from "../api/types";
import fixture from "./nativeDraft.fixture.json";
import { fromView, toView, viewFromTypes } from "./draftView";
import { editorDraft, nativeFromEditor } from "./nativeDraft";

export const nativeFixture = () => structuredClone(fixture) as NativeDraft;

describe("v3 editor adapter", () => {
  it("preserves native roles, ordered duplicate readings, absent fields and semantic data", () => {
    const original = nativeFixture();
    const edited = editorDraft(original);
    edited.object_types[0].name = "供应商显示名";
    const saved = nativeFromEditor(original, edited) as NativeDraft;
    expect(saved.object_types[0].concept).toBe("supplier");
    expect(saved.link_types).toEqual(original.link_types);
    expect(saved.value_types).toEqual(original.value_types);
    expect(saved.ai_context).toEqual(original.ai_context);
    expect(saved.semantic_models).toEqual(original.semantic_models);
    expect(saved.native_presence).toEqual(original.native_presence);
    expect(saved.object_types[1].native_presence).not.toContain("description");
  });
  it("keeps ValueType-owned ordered rules when an entity is edited through DraftView", () => {
    const original = nativeFixture();
    const view = toView(original);
    view.object_types[0].description = "changed";
    const saved = fromView(original, view) as NativeDraft;
    expect(saved.value_types[0].requires).toEqual(original.value_types[0].requires);
    expect(saved.rules.filter(r => r.owner_kind === "value_type")).toEqual(original.rules.filter(r => r.owner_kind === "value_type"));
    expect(saved.link_types[1]).toEqual(original.link_types[1]);
  });
  it("updates binary endpoint roles while retaining native identity and untouched n-ary links", () => {
    const original = nativeFixture();
    const edited = editorDraft(original);
    edited.link_types[0].target_type_id = original.object_types[0].id;
    const saved = nativeFromEditor(original, edited) as NativeDraft;
    expect(saved.link_types[0].roles[0].id).toBe(original.link_types[0].roles[0].id);
    expect(saved.link_types[0].roles[0].concept.ref).toBe(original.object_types[0].id);
    expect(saved.link_types[1]).toEqual(original.link_types[1]);
    expect(saved.mappings).toEqual([]);
  });
  it.each([
    [false, false], [false, true], [true, false], [true, true],
  ])("copies only explicit names for new binary links (named=%s, reverse=%s)", (named, reverse) => {
    const original = nativeFixture();
    const edited = editorDraft(original);
    const sourceName = named ? "sender" : undefined;
    const targetName = named ? "recipient" : undefined;
    edited.link_types.push({
      ...edited.link_types[0], id: crypto.randomUUID(), name: "客户发起", technical_name: "initiated_by",
      source_type_id: original.object_types[0].id, target_type_id: original.object_types[1].id,
      multiplicity: reverse ? "one_to_many" : "many_to_one",
      source_role_name: sourceName, target_role_name: targetName,
    });
    const saved = nativeFromEditor(original, edited) as NativeDraft;
    const link = saved.link_types.at(-1)!;
    expect(link.roles[0].name ?? null).toBe((reverse ? sourceName : targetName) ?? null);
    expect(link.owner_role_name ?? null).toBe((reverse ? targetName : sourceName) ?? null);
    expect(link.roles[0].native_presence?.includes("name")).toBe(named);
    const reopened = editorDraft(saved).link_types.at(-1)!;
    expect(reopened.source_role_name ?? null).toBe(sourceName ?? null);
    expect(reopened.target_role_name ?? null).toBe(targetName ?? null);
  });
  it("keeps an unnamed role when concept display labels change and clears explicit names", () => {
    const original = nativeFixture();
    original.link_types[0].roles[0].name = null;
    original.link_types[0].roles[0].native_presence = [];
    const edited = editorDraft(original);
    edited.object_types[0].name = "客户";
    const saved = nativeFromEditor(original, edited) as NativeDraft;
    expect(saved.link_types[0].roles[0].name).toBeNull();
    expect(saved.link_types[0].roles[0].native_presence).not.toContain("name");
    const named = editorDraft(saved);
    named.link_types[0].target_role_name = "buyer";
    const withName = nativeFromEditor(saved, named) as NativeDraft;
    expect(withName.link_types[0].roles[0].name).toBe("buyer");
    const cleared = editorDraft(withName);
    cleared.link_types[0].target_role_name = null;
    const result = nativeFromEditor(withName, cleared) as NativeDraft;
    expect(result.link_types[0].roles[0].name).toBeNull();
    expect(result.link_types[0].roles[0].native_presence).not.toContain("name");
  });

});

describe("P2 concept context", () => {
  it.each(["object_type", "value_type"] as const)("stores %s context only under the stable ID extension", kind => {
    const original = nativeFixture();
    const id = (kind === "object_type" ? original.object_types : original.value_types)[0].id;
    original.extension_v4.concept_context = { [id]: { synonyms: ["旧别名", "旧别名"], instructions: "原说明" } };
    const edited = editorDraft(original);
    const concept = (kind === "object_type" ? edited.object_types : edited.value_types!)[0];
    expect(concept.concept_context?.synonyms).toEqual(["旧别名", "旧别名"]);
    concept.concept_context = { synonyms: ["新别名", "新别名"], instructions: "平台口径" };
    const saved = nativeFromEditor(original, edited) as NativeDraft;
    expect(saved.extension_v4.concept_context?.[id]).toEqual(concept.concept_context);
    expect(saved.object_types).toEqual(original.object_types);
    expect(saved.value_types).toEqual(original.value_types);
    expect(saved.ai_context).toEqual(original.ai_context);
    expect(saved.semantic_models).toEqual(original.semantic_models);
    expect(editorDraft(saved).value_types).toHaveLength(original.value_types.length);
    expect(saved.object_types[0]).not.toHaveProperty("concept_context");
    expect(original.extension_v4.concept_context[id].synonyms).toEqual(["旧别名", "旧别名"]);
  });
});


it("keeps public value concept context in the catalog projection", () => {
  const value = nativeFixture().value_types[0];
  const context = { synonyms: ["金额别名"], instructions: "金额口径" };
  const view = viewFromTypes("workspace", [{ ...value, kind: "value_type", concept_context: context }]);
  expect(view.value_types?.[0]).toMatchObject({ id: value.id, concept_kind: "value_type", concept_context: context });
  expect(view.object_types).toEqual([]);
});
