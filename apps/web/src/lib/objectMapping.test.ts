import { describe, expect, it } from "vitest";
import { example } from "../test/drafts";
import { bindingMode } from "./coreModel";
import { objectMapping } from "./objectMapping";
import { addSource, chooseIdentifier, setInheritedLinkBinding } from "./objectMappingEditing";
import { relationEditReason } from "./relationEditing";

const draft = example("06-inheritance");
const byName = (name: string) => draft.object_types.find((o) => o.name === name)!;

describe("object mapping view", () => {
  it("resolves the four ways an object gets instances and returns unbound when descendants have no mapping", () => {
    expect(bindingMode(draft, byName("party").id)).toBe("independent");
    expect(bindingMode(draft, byName("person").id)).toBe("shared_parent");
    expect(bindingMode(draft, byName("asset").id)).toBe("virtual");
    expect(bindingMode(draft, byName("device").id)).toBe("independent");

    const unmappedAsset = {
      ...draft,
      mappings: draft.mappings.filter((m) => m.type_id !== byName("device").id && m.type_id !== byName("vehicle").id),
    };
    expect(bindingMode(unmappedAsset, byName("asset").id)).toBe("unbound");
  });
  it("shares the parent's main source and adds the child's extension", () => {
    const person = objectMapping(draft, byName("person"));
    expect(person.sources.map((s) => [s.id, s.ownerTypeId === byName("party").id])).toEqual([
      ["extension", false],
      ["main", true],
    ]);
    expect(person.main?.dataset?.name).toBe("parties");
    const partyNo = person.properties.find((p) => p.property.name === "party_no")!;
    expect(partyNo.inheritedFrom).toBe(byName("party").id);
    expect(partyNo.boundBy).toBe(byName("party").id);
  });
  it("binds an inherited relation locally on a concrete child of a virtual parent and blocks editing on shared_parent", () => {
    const device = byName("device");
    const link = draft.link_types.find((l) => (l.display_name || l.name) === "responsible_party")!;
    const responsible = draft.properties.find((p) => p.name === "responsible_no")!;
    const partyNo = draft.properties.find((p) => p.name === "party_no")!;
    const next = setInheritedLinkBinding(draft, device.id, link.id, {
      kind: "direct",
      source_property_ids: [responsible.id],
      target_property_ids: [partyNo.id],
    });
    const relation = objectMapping(next, next.object_types.find((o) => o.id === device.id)!).relations.find((r) => r.definition.id === link.id)!;
    expect(relation.local).toBe(true);
    expect(relationEditReason(next, device.id, relation)).toBeNull();
    expect(next.link_types.find((l) => l.id === link.id)).toEqual(link);

    const person = byName("person");
    const inheritedOnShared = objectMapping(draft, person).relations.find((r) => r.inheritedFrom)!;
    expect(relationEditReason(draft, person.id, inheritedOnShared)).toBe("继承关系使用父对象的绑定，请在父对象上修改。");
  });
  it("names extra sources side1, side2 and makes one property the identifier", () => {
    const party = byName("party");
    const { draft: next, sourceId } = addSource(draft, party.id, draft.datasets[1].id);
    expect(sourceId).toBe("side1");
    const name = draft.properties.find((p) => p.owner_type_id === party.id && p.name === "name")!;
    const chosen = chooseIdentifier(next, party.id, name.id).properties.filter((p) => p.owner_type_id === party.id && p.identifier);
    expect(chosen.map((p) => p.name)).toEqual(["name"]);
  });
});
