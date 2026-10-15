import { useState } from "react";
import { isObject, type PanelProps } from "../../lib/elementModel";
import { objectMapping } from "../../lib/objectMapping";
import { RelationCards } from "./RelationCards";
import { relationDeleteReason } from "../../lib/relationEditing";
import { ReadonlyIcon } from "./MappingWidgets";

export function LinkMappingPanel(props: PanelProps) {
  const [branchIndex, setBranchIndex] = useState(0);
  const { draft, type, nativeDraft, editing } = props;
  if (isObject(type)) return null;
  const owner = draft.object_types.find((o) => o.id === (type.owner_ref?.ref ?? type.source_type_id));
  const relation = owner ? objectMapping(draft, owner, nativeDraft).relations.find((r) => r.definition.id === type.id) : undefined;
  return <>{editing && <div className="om-mapping-tools"><button type="button" className="button button--secondary" disabled>删除</button><ReadonlyIcon reason={relationDeleteReason} /></div>}<RelationCards {...props} relation={relation ?? { definition: type, incoming: false, branches: [] }} branchIndex={branchIndex} onBranch={setBranchIndex} /></>;
}
