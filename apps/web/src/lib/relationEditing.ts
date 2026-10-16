import type { Draft, LinkType, UUID } from "../api/types";
import { bindingMode, byId } from "./coreModel";
import type { MappedRelation } from "./objectMapping";

export function relationEndpoints(draft: Draft, definition: LinkType) {
  return {
    sourceId: definition.source_type_id,
    targetId: definition.target_type_id,
    source: byId(draft.object_types, definition.source_type_id),
    target: byId(draft.object_types, definition.target_type_id),
  };
}

/**
 * Why the object inspector may not edit this relation's binding, or null.
 * A link's own data_join belongs to the link's save scope; only a concrete
 * child of a virtual parent binds an inherited link locally.
 */
export function relationEditReason(draft: Draft, viewingTypeId: UUID, relation: MappedRelation): string | null {
  if (relation.inheritedFrom) {
    if (bindingMode(draft, viewingTypeId) === "shared_parent" || bindingMode(draft, relation.inheritedFrom) !== "virtual") {
      return "继承关系使用父对象的绑定，请在父对象上修改。";
    }
    return null;
  }
  return "关系的数据绑定在关系里配置，请打开关系编辑。";
}
