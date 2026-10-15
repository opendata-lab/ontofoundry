import { describe, expect, it } from "vitest";
import { editorDraft, nativeFromEditor } from "./nativeDraft";
import { nativeMappingFixture } from "./objectMapping.fixture";
import { entryFrom, objectMapping } from "./objectMapping";
import {
  chooseIdentifier,
  mappingChangesForSave,
  mappingSaveError,
  propertyEntryChange,
  propertyReadonly,
} from "./objectMappingEditing";
import type { LegacyDraft, MappingNode } from "../api/types";

describe("native mapping projection and editing", () => {
  it("retains an invalid constant's editor mode across tabs and rejects it before saving", () => {
    const native = nativeMappingFixture();
    let draft = editorDraft(native);
    const props = () => ({
      nativeDraft: native, draft, type: draft.object_types[0], editing: true,
      change: (next: LegacyDraft) => { draft = next; }, open: () => {},
    });
    const entry = objectMapping(draft, draft.object_types[0], native).properties[0].entries[0];
    propertyEntryChange(props(), draft.properties[0], 0, {
      ...entry, mode: "constant", expression: "未加引号的值",
    });
    expect(objectMapping(draft, draft.object_types[0], native).properties[0].entries[0].mode).toBe("constant");
    expect(mappingSaveError(props())).toContain("常量格式无效");
    expect(nativeFromEditor(native, draft)).not.toHaveProperty("_mapping_modes");
  });
  it("preserves cross-dataset expressions and makes the flattened field editor read-only", () => {
    const native = nativeMappingFixture();
    (native.mapping_nodes as MappingNode[]).find((node) => node.id === "code-value")!.expression =
      "suppliers.code + events.owner";
    const draft = editorDraft(native);
    const type = draft.object_types[0];
    const record = objectMapping(draft, type, native);
    expect(record.properties[0].entries[0].expression).toBe("suppliers.code + events.owner");
    expect(propertyReadonly({ draft, nativeDraft: native, type, editing: true, change: () => {}, open: () => {} }, draft.properties[0]))
      .toContain("同一表达式引用多个数据集");
  });
  it("preserves qualified-looking SQL literals and removes only cleared optional bindings on save", () => {
    const native = nativeMappingFixture();
    let draft = editorDraft(native);
    const record = objectMapping(draft, draft.object_types[0], native);
    expect(
      entryFrom("'events.ref'", record.models[0].datasets).expression,
    ).toBe("'events.ref'");
    const props = () => ({
      nativeDraft: native,
      draft,
      type: draft.object_types[0],
      editing: true,
      change: (next: LegacyDraft) => {
        draft = next;
      },
      open: () => {},
    });
    propertyEntryChange(props(), draft.properties[1], 0, {
      value: "",
      expression: "name",
      mode: "field",
      dataset: record.models[0].datasets[0],
    });
    const row = objectMapping(draft, draft.object_types[0], native)
      .properties[1];
    const clearedId = row.entries[0].nodeId;
    propertyEntryChange(props(), row.property, 0, {
      ...row.entries[0],
      expression: "",
    });
    const nodes = mappingChangesForSave(draft)[0].nodes!;
    expect(nodes.some((n) => n.id === clearedId)).toBe(false);
    expect(nodes.find((n) => n.id === "code-value")?.expression).toBe(
      "suppliers.code",
    );
    expect(nodes.find((n) => n.id === "simple-value")?.expression).toBe(
      "events.ref",
    );
  });
  it("counts properties once across multiple sources and keeps native constants readable", () => {
    const native = nativeMappingFixture();
    const nodes = native.mapping_nodes as MappingNode[];
    nodes.push(
      {
        id: "code-other",
        parent_id: "properties",
        kind: "link",
        slot: "children",
        relationship: "code",
        concept_mapping_id: "cm-s",
      },
      {
        id: "code-other-value",
        parent_id: "code-other",
        kind: "object",
        slot: "object_mapping",
        expression: "events.owner",
        concept_mapping_id: "cm-s",
      },
    );
    const record = objectMapping(
      editorDraft(native),
      editorDraft(native).object_types[0],
      native,
    );
    expect(record.properties[0].entries.map((e) => e.dataset?.source)).toEqual([
      "public.dim_supplier",
      "public.fact_calls",
    ]);
    expect(record.covered).toBe(1);
    expect(record.state).toBe("partial");
    expect(record.relations[1].branches[0].roles[1].parts[0].mode).toBe(
      "constant",
    );
  });
  it("edits a second source without deleting relation branches, metadata or identifiers", () => {
    const native = nativeMappingFixture();
    let draft = editorDraft(native);
    const property = draft.properties[0];
    const props = () => ({
      nativeDraft: native,
      draft,
      type: draft.object_types[0],
      editing: true,
      change: (next: LegacyDraft) => {
        draft = next;
      },
      open: () => {},
    });
    const record = objectMapping(draft, draft.object_types[0], native);
    propertyEntryChange(props(), property, 1, {
      value: "",
      expression: "supplier_code",
      mode: "field",
      dataset: record.models[0].datasets[2],
    });
    const next = objectMapping(draft, draft.object_types[0], native);
    expect(next.properties[0].entries).toHaveLength(2);
    expect(next.covered).toBe(1);
    const staged = draft._semantic_changes![0].nodes!;
    expect(
      staged.find((n) => n.id === "record-count-value-0")?.expression,
    ).toBe("10");
    expect(nativeFromEditor(native, draft).object_types).toEqual(
      native.object_types,
    );
  });
  it("chooses the identifier using the row toggle and synchronizes native identify_by", () => {
    const native = nativeMappingFixture();
    let draft = editorDraft(native);
    const props = () => ({
      nativeDraft: native,
      draft,
      type: draft.object_types[0],
      editing: true,
      change: (next: LegacyDraft) => {
        draft = next;
      },
      open: () => {},
    });
    const record = objectMapping(draft, draft.object_types[0], native);
    propertyEntryChange(props(), draft.properties[1], 0, {
      value: "",
      expression: "name",
      mode: "field",
      dataset: record.models[0].datasets[0],
    });
    chooseIdentifier(props(), draft.properties[1]);
    expect(draft.properties.map((p) => p.identifier)).toEqual([false, true]);
    expect(
      draft._semantic_changes![0].nodes!.find((n) => n.id === "key-s")
        ?.expression,
    ).toBe("suppliers.name");
    expect(nativeFromEditor(native, draft).object_types[0]).toMatchObject({
      identify_by: ["name"],
    });
  });
  it("fills an empty owner root when the identifier is chosen after the first field binding", () => {
    const native = nativeMappingFixture();
    native.mapping_nodes = (native.mapping_nodes as MappingNode[])
      .filter((node) => node.concept_mapping_id !== "cm-s");
    let draft = editorDraft(native);
    const props = () => ({
      nativeDraft: native,
      draft,
      type: draft.object_types[0],
      editing: true,
      change: (next: LegacyDraft) => { draft = next; },
      open: () => {},
    });
    const dataset = objectMapping(draft, draft.object_types[0], native).models[0].datasets[0];
    propertyEntryChange(props(), draft.properties[1], 0, {
      value: "", expression: "name", mode: "field", dataset,
    });
    chooseIdentifier(props(), draft.properties[1]);
    const nodes = mappingChangesForSave(draft)[0].nodes!;
    expect(nodes.find((node) => node.slot === "object_mappings")?.expression).toBe("suppliers.name");
    expect(nodes.find((node) => node.slot === "object_mapping" && !node.concept)?.expression).toBe("suppliers.name");
  });
});
