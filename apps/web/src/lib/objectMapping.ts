// How one object is bound to registered datasets, read from the core-1 draft.
// The mapping page and the object inspector both show this view.
import type {
  BindingStatus,
  DataJoin,
  DataMapping,
  Dataset,
  Draft,
  FieldBinding,
  LinkType,
  ObjectType,
  Property,
  UUID,
} from "../api/types";
import {
  bindingMode,
  byId,
  effectiveLinks,
  effectiveProperties,
  effectiveSources,
  lineage,
  mappingFor,
  type BindingMode,
  type ResolvedSource,
} from "./coreModel";

export type MappedProperty = {
  property: Property;
  inheritedFrom: UUID | null;
  binding: FieldBinding | undefined;
  /** Object whose mapping provides the binding (an ancestor when shared). */
  boundBy: UUID | null;
};

export type MappedRelation = {
  definition: LinkType;
  direction: "forward" | "reverse";
  inheritedFrom: UUID | null;
  /** The link's own data_join, or the local binding of an inherited link. */
  join: DataJoin | null;
  local: boolean;
};

export type ObjectMapping = {
  object: ObjectType;
  mode: BindingMode;
  mapping: DataMapping | undefined;
  sources: ResolvedSource[];
  main: ResolvedSource | undefined;
  properties: MappedProperty[];
  relations: MappedRelation[];
  covered: number;
  total: number;
  state: "mapped" | "partial" | "unmapped";
  label: string;
};

export const shortObjectName = (object: { name: string }) => object.name.split(/[；。]/)[0];

/** Registered column names of a dataset; [] when no column list was provided. */
export function sourceColumns(dataset: Dataset | undefined): string[] {
  return (dataset?.columns ?? []).map((c) => c.name);
}

function bindingFor(draft: Draft, typeId: UUID, technicalName: string) {
  for (const id of lineage(draft, typeId)) {
    const mapping = mappingFor(draft, id);
    const binding = mapping?.fields[technicalName];
    if (binding) return { binding, boundBy: id };
    if (mapping?.binding_mode === "independent") break;
  }
  return { binding: undefined, boundBy: null };
}

export function objectMapping(draft: Draft, object: ObjectType): ObjectMapping {
  const mapping = mappingFor(draft, object.id);
  const sources = effectiveSources(draft, object.id);
  const properties = effectiveProperties(draft, object.id).map(({ definition, inheritedFrom }) => ({
    property: definition,
    inheritedFrom,
    ...bindingFor(draft, object.id, definition.technical_name),
  }));
  const relations = effectiveLinks(draft, object.id, true).map(({ definition, direction, inheritedFrom }) => {
    const local = inheritedFrom ? mapping?.inherited_link_bindings[definition.id] : undefined;
    return {
      definition,
      direction,
      inheritedFrom,
      join: local ?? definition.data_join ?? null,
      local: !!local,
    };
  });
  const total = properties.length;
  const covered = properties.filter((p) => p.binding).length;
  const mode = bindingMode(draft, object.id);
  const state = covered === 0 ? "unmapped" : covered === total ? "mapped" : "partial";
  const label =
    mode === "virtual"
      ? "虚拟父对象，实例来自子对象"
      : mode === "unbound"
        ? "未绑定数据集"
        : state === "mapped"
          ? "已映射"
          : state === "partial"
            ? `已映射 ${covered}/${total} 个属性`
            : "未映射属性";
  return {
    object,
    mode,
    mapping,
    sources,
    main: sources.find((s) => s.id === "main"),
    properties,
    relations,
    covered,
    total,
    state,
    label,
  };
}

export function objectMappings(draft: Draft): ObjectMapping[] {
  return draft.object_types.map((object) => objectMapping(draft, object));
}

/** Datasets used by a mapping, in source order. */
export function mappingDatasets(draft: Draft, mapping: DataMapping): Dataset[] {
  return mapping.sources
    .map((source) => byId(draft.datasets, source.dataset_id))
    .filter((dataset): dataset is Dataset => !!dataset);
}

export function bindingText(binding: FieldBinding | undefined): string {
  if (!binding) return "未绑定";
  return binding.kind === "column" ? `${binding.source_id}.${binding.column}` : binding.expression;
}

export const BINDING_STATUS: Record<BindingStatus, { color: string; text: string }> = {
  bound: { color: "success", text: "已绑定" },
  unbound: { color: "default", text: "未绑定" },
  virtual: { color: "processing", text: "实例来自子对象" },
  missing_key: { color: "warning", text: "缺少键列" },
  cross_connection: { color: "error", text: "跨连接" },
  metadata_stale: { color: "warning", text: "元数据待更新" },
  forbidden: { color: "default", text: "无权查看" },
};

export const BINDING_MODES: Record<BindingMode, string> = {
  independent: "独立绑定",
  shared_parent: "共用父对象数据",
  virtual: "虚拟父对象",
  unbound: "未绑定",
};

export function sourceLabel(source: Pick<ResolvedSource, "id">, membership?: string | null, shared = false) {
  if (source.id === "main") return "主表";
  if (source.id === membership) return "成员扩展表";
  return shared ? `扩展表 ${source.id}` : `附表 ${source.id}`;
}
