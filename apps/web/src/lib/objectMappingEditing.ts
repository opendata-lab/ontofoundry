import type {
  LegacyDraft,
  MappingNode,
  PropertyElement,
  SemanticConceptMapping,
  SemanticDataset,
} from "../api/types";
import type { PanelProps } from "./elementModel";
import { inheritedProperties, isObject } from "./elementModel";
import { cleanNodes } from "./semanticEditing";
import { newId } from "./id";
import {
  mappingModels,
  nativeEntryValue,
  objectMapping,
  readonlyReason,
  type MappingEntry,
} from "./objectMapping";

export function stageMapping(
  draft: LegacyDraft,
  cm: SemanticConceptMapping,
  nodes: MappingNode[],
  parentId?: string,
): LegacyDraft {
  const previous = draft._semantic_changes?.find((c) => c.id === cm.id);
  return {
    ...draft,
    _semantic_changes: [
      ...(draft._semantic_changes ?? []).filter((c) => c.id !== cm.id),
      {
        kind: "concept_mapping",
        operation: previous?.operation ?? "update",
        id: cm.id,
        parent_id: previous?.parent_id ?? parentId,
        values: { concept_id: cm.concept_id, ...previous?.values },
        nodes: cleanNodes(nodes),
      },
    ],
  };
}
export function propertyEntryChange(
  props: PanelProps,
  property: PropertyElement,
  index: number,
  entry: MappingEntry,
) {
  if (!isObject(props.type)) return;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  let cm = record.mappings[0];
  if (!props.nativeDraft) return;
  let base = props.draft;
  if (!cm) {
    const model = record.models.find((m) =>
      m.datasets.some((d) => d.id === entry.dataset?.id),
    );
    if (!model) return;
    cm = {
      id: newId(),
      concept_id: { kind: "object_type", ref: props.type.id },
      nodes: [],
    };
    base = {
      ...base,
      _semantic_changes: [
        ...(base._semantic_changes ?? []),
        {
          kind: "concept_mapping",
          operation: "create",
          id: cm.id,
          parent_id: model.id,
          values: { concept_id: cm.concept_id },
          nodes: [],
        },
      ],
    };
  }
  let nodes = cm.nodes.map((n) => ({ ...n }));
  const value = nativeEntryValue(entry);
  const node = entry.nodeId
    ? nodes.find((n) => n.id === entry.nodeId)
    : undefined;
  const entryId = node?.id ?? newId();
  if (node) node.expression = value;
  else {
    let host = nodes.find(
      (n) => n.slot === "link_mappings" && !n.parent_id && !n.relationship,
    );
    if (!host) {
      host = {
        id: newId(),
        parent_id: null,
        kind: "link",
        slot: "link_mappings",
      };
      nodes.push(host, {
        id: newId(),
        parent_id: host.id,
        kind: "object",
        slot: "object_mapping",
        expression: record.keys[0]?.value ?? "",
      });
    }
    const link: MappingNode = {
      id: newId(),
      parent_id: host.id,
      kind: "link",
      slot: "children",
      relationship: property.technical_name,
    };
    nodes.push(link, {
      id: entryId,
      parent_id: link.id,
      kind: "object",
      slot: "object_mapping",
      concept: property.roles?.[0]?.concept ?? {
        kind: "builtin",
        ref: "String",
      },
      expression: value,
    });
    // A suggested identifier is not an actual property node until bound here.
    void index;
  }
  if (
    property.identifier &&
    value &&
    record.keys.length <= 1 &&
    (index === 0 || !record.keys.length)
  ) {
    const oldKey = record.keys[0]?.value;
    nodes = nodes.map((n) =>
      n.slot === "object_mappings" ||
      (n.kind === "object" &&
        !n.concept &&
        (!n.expression || n.expression === oldKey))
        ? { ...n, expression: value }
        : n,
    );
    if (!nodes.some((n) => n.slot === "object_mappings"))
      nodes.unshift({
        id: newId(),
        parent_id: null,
        kind: "object",
        slot: "object_mappings",
        expression: value,
      });
  }
  props.change({
    ...stageMapping(base, cm, nodes),
    _mapping_modes: { ...base._mapping_modes, [entryId]: entry.mode },
  });
}
export function selectMappingDataset(props: PanelProps, dataset: SemanticDataset) {
  if (!isObject(props.type)) return;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  let next = record.mappings.length ? props.draft : {
    ...props.draft,
    mappings: props.draft.mappings.filter((m) => m.type_id !== props.type.id),
  };
  for (const row of record.properties) {
    if (propertyReadonly(props, row.property)) continue;
    row.entries.forEach((entry, index) => {
      if (entry.mode === "constant" ||
          (entry.dataset && entry.dataset.id !== record.mainDataset?.id)) return;
      propertyEntryChange({
        ...props, draft: next, change: (value) => { next = value; },
      }, row.property, index, { ...entry, dataset, expression: "", pending: false });
    });
  }
  props.change({
    ...next,
    _mapping_tables: { ...next._mapping_tables, [props.type.id]: dataset.id },
  });
}

export function tableReplacementReason(props: PanelProps): string | null {
  if (props.draft.mapping_status?.[props.type.id]?.state === "readonly")
    return `${readonlyReason(props.draft, props.type.id) ?? "当前映射不能通过单表表单替换"}；请在「数据映射 › 语义模型」中配置新的数据集。`;
  if (!isObject(props.type)) return null;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  return props.draft._semantic_changes?.some((change) =>
    record.mappings.some((cm) => cm.id === change.id),
  ) ? "原生节点编辑已加入草稿；请先保存后替换来源表。" : null;
}
export function chooseIdentifier(props: PanelProps, property: PropertyElement) {
  if (!isObject(props.type)) return;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  const entry = record.properties
    .find((p) => p.property.id === property.id)
    ?.entries.find((e) => e.expression && !e.pending);
  let draft: LegacyDraft = {
    ...props.draft,
    properties: props.draft.properties.map((p) =>
      p.owner_type_id === props.type.id
        ? { ...p, identifier: p.id === property.id }
        : p,
    ),
  };
  if (record.mappings.length === 1 && !record.usesLegacyForm && entry) {
    const cm = record.mappings[0],
      oldKey = record.keys[0]?.value;
    const value = nativeEntryValue(entry);
    const nodes = cm.nodes.map((n) =>
      n.slot === "object_mappings" ||
      (n.kind === "object" && !n.concept && (!n.expression || n.expression === oldKey))
        ? { ...n, expression: value }
        : n,
    );
    if (!nodes.some((n) => n.slot === "object_mappings"))
      nodes.unshift({
        id: newId(),
        parent_id: null,
        kind: "object",
        slot: "object_mappings",
        expression: value,
      });
    draft = stageMapping(draft, cm, nodes);
  } else {
    draft = {
      ...draft,
      mappings: draft.mappings.map((m) =>
        m.type_id === props.type.id && entry
          ? { ...m, key_column: entry.expression }
          : m,
      ),
    };
  }
  props.change(draft);
}
export function relationEntryChange(
  props: PanelProps,
  entry: MappingEntry,
  next: MappingEntry,
): LegacyDraft {
  const cm = mappingModels(props.draft, props.nativeDraft)
    .flatMap((m) => m.concept_mappings ?? [])
    .find((cm) => cm.id === entry.mappingId);
  if (!cm || !entry.nodeId) return props.draft;
  const staged = stageMapping(
    props.draft,
    cm,
    cm.nodes.map((n) =>
      n.id === entry.nodeId ? { ...n, expression: nativeEntryValue(next) } : n,
    ),
  );
  return {
    ...staged,
    _mapping_modes: { ...staged._mapping_modes, [entry.nodeId]: next.mode },
  };
}
export function propertyReadonly(
  props: PanelProps,
  property: PropertyElement,
): string | null {
  if (!isObject(props.type)) return null;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  if ((property.roles?.length ?? 1) > 1)
    return "属性包含多个角色；单行字段编辑不能保留完整角色结构，请在「数据映射 › 语义模型 › 概念映射」中编辑映射树。";
  const expressionReason = record.properties.find((row) => row.property.id === property.id)
    ?.entries.find((entry) => entry.readonlyReason)?.readonlyReason;
  if (expressionReason) return expressionReason;
  if (record.mappings.length > 1)
    return `${readonlyReason(props.draft, props.type.id) ?? "同一概念有多个映射"}；不能确定属性所属的映射，请在「数据映射 › 语义模型 › 概念映射」中选择映射树。`;
  const cm = record.mappings[0];
  const links =
    cm?.nodes.filter(
      (n) => n.kind === "link" && n.relationship === property.technical_name,
    ) ?? [];
  if (
    links.some(
      (link) =>
        !cm!.nodes.some(
          (n) =>
            n.parent_id === link.id &&
            n.slot === "object_mapping" &&
            n.expression != null &&
            !cm!.nodes.some(
              (child) =>
                child.parent_id === n.id && child.slot === "referent_mappings",
            ),
        ),
    )
  ) {
    return `${readonlyReason(props.draft, props.type.id) ?? "属性映射含嵌套结构或 referent 引用"}；请在「数据映射 › 语义模型 › 概念映射」中编辑完整映射树。`;
  }
  return null;
}
export function mappingSaveError(props: PanelProps): string | null {
  if (!isObject(props.type)) return null;
  const record = objectMapping(props.draft, props.type, props.nativeDraft);
  const mapping = props.draft.mappings.find((m) => m.type_id === props.type.id);
  for (const cm of record.mappings) {
    for (const node of cm.nodes) {
      if (props.draft._mapping_modes?.[node.id] === "constant" &&
          node.expression && !/^(?:'(?:[^']|'')*'|[+-]?\d+(?:\.\d+)?|true|false|null)$/i.test(node.expression.trim()))
        return "常量格式无效：字符串须使用单引号。";
    }
  }
  if (mapping && !mapping.key_column) return "请在已映射的属性行标记实例标识。";
  const changed = new Set(
    (props.draft._semantic_changes ?? [])
      .filter((c) => c.kind === "concept_mapping")
      .map((c) => c.id),
  );
  if (
    record.keys.length <= 1 &&
    record.properties.some(
      (row) =>
        row.property.identifier &&
        !row.entries.some((e) => e.expression && !e.pending),
    ) &&
    changed.size
  )
    return "请为实例标识属性选择字段。";
  if (changed.size && !record.keys.some((e) => e.expression))
    return "请在已映射的属性行标记实例标识。";
  for (const row of record.properties) {
    for (const e of row.entries) {
      if (
        e.mode === "constant" &&
        e.expression &&
        !/^(?:'(?:[^']|'')*'|[+-]?\d+(?:\.\d+)?|true|false|null)$/i.test(
          e.expression,
        )
      )
        return `${row.property.name}：常量格式无效。`;
    }
  }
  return null;
}

/** Clearing an optional field removes its simple binding, preserving other native nodes. */
export function mappingChangesForSave(draft: LegacyDraft) {
  return (draft._semantic_changes ?? []).map((change) => {
    if (change.kind !== "concept_mapping" || !change.nodes) return change;
    const concept = change.values.concept_id as { ref?: string } | undefined;
    const owner = draft.object_types.find(
      (object) => object.id === concept?.ref,
    );
    if (!owner) return change;
    const properties = new Set(
      [
        ...draft.properties.filter((p) => p.owner_type_id === owner.id),
        ...inheritedProperties(draft, owner).map((p) => p.property),
      ].map((p) => p.technical_name),
    );
    const removed = new Set<string>();
    for (const link of change.nodes) {
      if (
        link.kind !== "link" ||
        !link.relationship ||
        !properties.has(link.relationship)
      )
        continue;
      const children = change.nodes.filter((n) => n.parent_id === link.id);
      if (
        children.length !== 1 ||
        children[0].slot !== "object_mapping" ||
        children[0].expression !== "" ||
        change.nodes.some((n) => n.parent_id === children[0].id)
      )
        continue;
      removed.add(link.id);
      removed.add(children[0].id);
    }
    return { ...change, nodes: change.nodes.filter((n) => !removed.has(n.id)) };
  });
}
