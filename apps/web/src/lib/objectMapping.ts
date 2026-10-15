import type {
  DataMapping,
  LegacyDraft,
  LinkTypeElement,
  MappingNode,
  NativeDraft,
  ObjectTypeElement,
  PropertyElement,
  SemanticConceptMapping,
  SemanticDataset,
  SemanticModel,
} from "../api/types";
import { inheritedProperties, relationsFor } from "./elementModel";
import { nativeSemanticModels } from "./semanticEditing";

export type MappingEntry = {
  value: string;
  expression: string;
  mode: "field" | "expression" | "constant";
  dataset?: SemanticDataset;
  referencedDatasets?: SemanticDataset[];
  nodeId?: string;
  mappingId?: string;
  pending?: boolean;
  label?: string;
  readonlyReason?: string;
};
export type MappedProperty = {
  property: PropertyElement;
  inherited: boolean;
  entries: MappingEntry[];
};
export type MappingBranch = {
  id: string;
  source: MappingEntry[];
  roles: {
    name: string;
    object: string;
    kind: string;
    parts: MappingEntry[];
  }[];
};
export type MappedRelation = {
  definition: LinkTypeElement;
  incoming: boolean;
  inherited?: boolean;
  inheritedFrom?: string;
  branches: MappingBranch[];
};
export type ObjectMapping = {
  object: ObjectTypeElement;
  properties: MappedProperty[];
  keys: MappingEntry[];
  mainDataset?: SemanticDataset;
  tables: SemanticDataset[];
  relations: MappedRelation[];
  models: SemanticModel[];
  mappings: SemanticConceptMapping[];
  usesLegacyForm: boolean;
  covered: number;
  total: number;
  state: "mapped" | "partial" | "unmapped";
  label: string;
};
export const shortObjectName = (object: { name: string }) =>
  object.name.split(/[；。]/)[0];
export const literal = (value: string) =>
  /^(?:'(?:[^']|'')*'|[+-]?\d+(?:\.\d+)?|true|false|null)$/i.test(value.trim());
export const fieldSQL = (field: SemanticDataset["fields"][number]) =>
  field.expression?.dialects?.find((d) => d.dialect === "ANSI_SQL")
    ?.expression ??
  field.expression?.dialects?.[0]?.expression ??
  field.name;
export function sourceColumns(dataset?: SemanticDataset): string[] {
  const words = new Set<string>();
  const stop = new Set(
    "CASE WHEN THEN ELSE END LOWER UPPER TRIM COALESCE NULL NULLIF IN IS NOT AND OR AS CAST VARCHAR INTEGER FLOAT DATE TRUE FALSE DISTINCT COUNT SUM AVG TO_CHAR SUBSTR CONCAT REPLACE".split(
      " ",
    ),
  );
  for (const field of dataset?.fields ?? []) {
    const sql = fieldSQL(field).replace(/'[^']*'/g, " ");
    const column = sql
      .trim()
      .match(
        /^(?:(?:[A-Za-z_]\w*|"(?:[^"]|"")+")\.)?([A-Za-z_]\w*|"(?:[^"]|"")+")$/,
      )?.[1];
    if (column && !literal(sql)) {
      words.add(
        column.startsWith('"')
          ? column.slice(1, -1).replaceAll('""', '"')
          : column,
      );
      continue;
    }
    for (const match of sql.matchAll(/\b[A-Za-z_]\w*\b/g)) {
      if (
        !stop.has(match[0].toUpperCase()) &&
        !/^\s*\(/.test(sql.slice(match.index! + match[0].length))
      )
        words.add(match[0]);
    }
  }
  return [...words];
}
export function mappingModels(
  draft: LegacyDraft,
  native?: NativeDraft,
): SemanticModel[] {
  if (!native) return [];
  return nativeSemanticModels(native).map((model) => ({
    ...model,
    concept_mappings: (model.concept_mappings ?? [])
      .map((cm) => {
        const change = draft._semantic_changes?.find(
          (c) => c.id === cm.id && c.kind === "concept_mapping",
        );
        return { ...cm, nodes: change?.nodes ?? cm.nodes };
      })
      .concat(
        (draft._semantic_changes ?? [])
          .filter(
            (c) =>
              c.kind === "concept_mapping" &&
              c.operation === "create" &&
              c.parent_id === model.id,
          )
          .map((c) => ({
            id: c.id,
            concept_id: c.values
              .concept_id as SemanticConceptMapping["concept_id"],
            nodes: c.nodes ?? [],
          })),
      ),
  }));
}
export function entryFrom(
  value: string,
  datasets: SemanticDataset[],
  node?: MappingNode,
  fallback?: SemanticDataset,
): MappingEntry {
  if (literal(value))
    return {
      value,
      expression: value,
      mode: "constant",
      nodeId: node?.id,
      mappingId: node?.concept_mapping_id,
    };
  const identifier = '(?:[A-Za-z_]\\w*|"(?:[^"]|"")+")';
  const references = [
    ...value
      .replace(/'(?:[^']|'')*'/g, (text) => " ".repeat(text.length))
      .matchAll(new RegExp(`(${identifier})\\.(${identifier})`, "g")),
  ];
  const unquote = (s: string) =>
    s.startsWith('"') ? s.slice(1, -1).replaceAll('""', '"') : s;
  const match = references.find((m) =>
    datasets.some((d) => d.name === unquote(m[1])),
  );
  const referencedTables = new Set(
    references
      .map((m) => datasets.find((d) => d.name === unquote(m[1]))?.id)
      .filter(Boolean),
  );
  const dataset = match
    ? datasets.find((d) => d.name === unquote(match[1]))
    : fallback;
  const expression = value.replace(
    new RegExp(`'(?:[^']|'')*'|(${identifier})\\.(${identifier})`, "g"),
    (full, table: string | undefined, field: string) => {
      if (!table) return full;
      const ds = datasets.find((d) => d.name === unquote(table));
      return ds
        ? fieldSQL(
            ds.fields.find((f) => f.name === unquote(field)) ??
              ({
                id: unquote(field),
                name: unquote(field),
                expression: { dialects: [] },
              } as SemanticDataset["fields"][number]),
          )
        : full;
    },
  );
  return {
    value,
    expression: referencedTables.size > 1 ? value : expression,
    dataset,
    referencedDatasets:
      referencedTables.size > 1
        ? datasets.filter((d) => referencedTables.has(d.id))
        : undefined,
    nodeId: node?.id,
    mappingId: node?.concept_mapping_id,
    readonlyReason:
      referencedTables.size > 1
        ? "同一表达式引用多个数据集；单行来源表不能完整表示该表达式，请在「数据映射 › 语义模型 › 概念映射」中编辑原始映射节点。"
        : undefined,
    mode: literal(expression)
      ? "constant"
      : !expression || /^(?:[A-Za-z_]\w*|"(?:[^"]|"")+")$/.test(expression)
        ? "field"
        : "expression",
  };
}
export function nativeEntryValue(entry: MappingEntry): string {
  if (!entry.expression || entry.mode === "constant") return entry.expression;
  const field = entry.dataset?.fields.find(
    (f) => fieldSQL(f) === entry.expression,
  );
  const quote = (s: string) =>
    /^[A-Za-z_]\w*$/.test(s) ? s : '"' + s.replaceAll('"', '""') + '"';
  if (entry.dataset && (field || entry.mode === "field"))
    return `${quote(entry.dataset.name)}.${quote(field?.name ?? entry.expression)}`;
  return entry.expression;
}
export function shortField(
  entry: MappingEntry,
  main?: SemanticDataset,
): string {
  const prefix =
    entry.dataset && entry.dataset.id !== main?.id
      ? `${entry.dataset.source.split(".").pop()}.`
      : "";
  const columns = sourceColumns(entry.dataset).filter((c) =>
    new RegExp(`\\b${c}\\b`).test(entry.expression.replace(/'[^']*'/g, " ")),
  );
  return columns.length
    ? columns.map((c) => prefix + c).join(" + ")
    : entry.expression
      ? (entry.mode === "field" ? prefix : "") + entry.expression
      : "—";
}
export function fullField(entry: MappingEntry): string {
  if (entry.readonlyReason) return entry.value;
  if (entry.dataset && entry.mode === "expression") {
    const text = entry.expression.replace(/'(?:[^']|'')*'/g, " ");
    const columns = sourceColumns(entry.dataset).filter((column) =>
      new RegExp(`\\b${column.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(
        text,
      ),
    );
    if (columns.length)
      return columns
        .map((column) => `${entry.dataset!.source}.${column}`)
        .join(" + ");
  }
  return entry.mode === "constant"
    ? entry.expression
    : entry.dataset
      ? `${entry.dataset.source}.${entry.expression}`
      : entry.expression || "—";
}
export const isMappedEntry = (entry: MappingEntry) =>
  !!entry.expression && !entry.pending;
export const branchDataset = (branch?: MappingBranch) =>
  branch?.source.find((e) => e.dataset)?.dataset ??
  branch?.roles.flatMap((r) => r.parts).find((e) => e.dataset)?.dataset;
function parts(nodes: MappingNode[], node?: MappingNode): MappingEntry[] {
  if (!node) return [];
  if (node.expression != null)
    return [
      {
        value: node.expression,
        expression: node.expression,
        mode: "field",
        nodeId: node.id,
        mappingId: node.concept_mapping_id,
      },
    ];
  const children = nodes.filter(
    (n) => n.parent_id === node.id && n.slot === "referent_mappings",
  );
  return children.flatMap((n) =>
    n.expression
      ? [
          {
            value: n.expression,
            expression: n.expression,
            mode: "field" as const,
            nodeId: n.id,
            mappingId: n.concept_mapping_id,
            label: n.relationship ?? undefined,
          },
        ]
      : parts(nodes, n),
  );
}
function legacyDataset(mapping: DataMapping): SemanticDataset {
  return {
    id: mapping.id,
    name: mapping.table_name,
    source: [mapping.schema_name, mapping.table_name].filter(Boolean).join("."),
    primary_key: [mapping.key_column],
    unique_keys: [],
    fields: [...new Set([mapping.key_column, ...Object.values(mapping.fields)])]
      .filter(Boolean)
      .map((name) => ({
        id: name,
        name,
        expression: { dialects: [{ dialect: "ANSI_SQL", expression: name }] },
      })),
  };
}
export function objectMapping(
  draft: LegacyDraft,
  object: ObjectTypeElement,
  native?: NativeDraft,
): ObjectMapping {
  const entry = (...args: Parameters<typeof entryFrom>) => {
    const value = entryFrom(...args);
    const mode = value.nodeId
      ? draft._mapping_modes?.[value.nodeId]
      : undefined;
    return { ...value, mode: mode ?? value.mode };
  };
  const models = mappingModels(draft, native);
  const mappings = models
    .flatMap((m) => m.concept_mappings ?? [])
    .filter((cm) => cm.concept_id.ref === object.id);
  const datasets = models.flatMap((m) => m.datasets);
  const datasetsFor = (mappingId?: string) =>
    models.find((m) => m.concept_mappings?.some((cm) => cm.id === mappingId))
      ?.datasets ?? datasets;
  const nodes = mappings.flatMap((cm) =>
    cm.nodes.map((n) => ({ ...n, concept_mapping_id: cm.id })),
  );
  const mapping = draft.mappings.find((m) => m.type_id === object.id);
  const simple = mapping ? legacyDataset(mapping) : undefined;
  // The legacy form is used when it was actually edited; native trees are read otherwise.
  const legacyChanged =
    native &&
    JSON.stringify(mapping) !==
      JSON.stringify(
        native._legacy_form?.mappings.find((m) => m.type_id === object.id),
      );
  const useLegacy = !nodes.length || legacyChanged;
  const keys = useLegacy
    ? mapping?.key_column
      ? [entry(mapping.key_column, [], undefined, simple)]
      : []
    : nodes
        .filter((n) => n.slot === "object_mappings")
        .flatMap((n) => parts(nodes, n))
        .map((e) => ({
          ...entry(
            e.value,
            datasetsFor(e.mappingId),
            nodes.find((n) => n.id === e.nodeId),
          ),
          label: e.label,
        }));
  const rows = [
    ...draft.properties
      .filter((p) => p.owner_type_id === object.id)
      .map((property) => ({ property, inherited: false })),
    ...inheritedProperties(draft, object).map(({ property }) => ({
      property,
      inherited: true,
    })),
  ];
  const properties = rows.map((row) => {
    const column = mapping?.fields[row.property.technical_name];
    let entries = useLegacy
      ? column
        ? [entry(column, [], undefined, simple)]
        : []
      : nodes
          .filter(
            (n) =>
              n.kind === "link" &&
              n.relationship === row.property.technical_name,
          )
          .flatMap((link) =>
            parts(
              nodes,
              nodes.find(
                (n) => n.parent_id === link.id && n.slot === "object_mapping",
              ),
            ),
          )
          .map((e) => ({
            ...entry(
              e.value,
              datasetsFor(e.mappingId),
              nodes.find((n) => n.id === e.nodeId),
              datasets.find(
                (d) => d.id === draft._mapping_tables?.[object.id],
              ) ?? keys.find((key) => key.mappingId === e.mappingId)?.dataset,
            ),
            label: e.label,
          }));
    if (!entries.length && row.property.identifier && keys.length === 1)
      entries = [{ ...keys[0], nodeId: undefined, pending: true }];
    const declaration = row.inherited
      ? native?.properties.find((p) => p.id === row.property.id)
      : undefined;
    const ref =
      declaration?.roles[0]?.concept ?? row.property.roles?.[0]?.concept;
    const builtin =
      ref?.kind === "value_type"
        ? native?.value_types
            .find((v) => v.id === ref.ref)
            ?.extends?.find((r) => r.kind === "builtin")?.ref
        : ref?.ref;
    const kinds: Record<string, string> = {
      String: "string",
      Integer: "integer",
      Decimal: "decimal",
      Float: "float",
      Boolean: "boolean",
      Date: "date",
      DateTime: "datetime",
    };
    const property =
      (!row.property.value_kind || row.property.value_kind === "unknown") &&
      builtin &&
      kinds[builtin]
        ? { ...row.property, value_kind: kinds[builtin] }
        : row.property;
    return { ...row, property, entries };
  });
  const mainDataset =
    datasets.find((d) => d.id === draft._mapping_tables?.[object.id]) ??
    keys.find((e) => e.dataset)?.dataset ??
    simple;
  const relations = relationsFor(draft, object).map(
    ({ definition, incoming, inherited, inheritedFrom }) => {
      const owner = definition.owner_ref?.ref ?? definition.source_type_id;
      const cms = models
        .flatMap((m) => m.concept_mappings ?? [])
        .filter((cm) => cm.concept_id.ref === owner);
      const ns = cms.flatMap((cm) =>
        cm.nodes.map((n) => ({ ...n, concept_mapping_id: cm.id })),
      );
      const branches: MappingBranch[] = ns
        .filter(
          (n) =>
            n.kind === "link" && n.relationship === definition.technical_name,
        )
        .map((node) => {
          const path: MappingNode[] = [];
          const seen = new Set<string>();
          let current: MappingNode | undefined = node;
          while (current && !seen.has(current.id)) {
            seen.add(current.id);
            path.unshift(current);
            current = ns.find((n) => n.id === current!.parent_id);
          }
          const objects = path
            .filter((n) => n.kind === "link")
            .map((n) =>
              ns.find(
                (o) => o.parent_id === n.id && o.slot === "object_mapping",
              ),
            )
            .filter((n) => n !== undefined);
          const read = (n?: MappingNode) =>
            parts(ns, n).map((e) => ({
              ...entry(
                e.value,
                datasetsFor(e.mappingId),
                ns.find((n) => n.id === e.nodeId),
              ),
              label: e.label,
            }));
          return {
            id: node.id,
            source: read(objects[0]),
            roles: objects.slice(1).map((n, i) => ({
              name:
                definition.roles?.[i]?.name ??
                draft.object_types.find((t) => t.id === n.concept?.ref)?.name ??
                "字段",
              object: n.concept?.ref ?? "",
              kind: n.concept?.kind ?? "builtin",
              parts: read(n),
            })),
          };
        });
      if (!branches.length && definition.data_join) {
        const src = draft.mappings.find((m) => m.type_id === owner);
        const join = definition.data_join;
        branches.push({
          id: definition.id,
          source: src
            ? [entry(src.key_column, [], undefined, legacyDataset(src))]
            : [],
          roles: [
            {
              name: definition.target_role_name ?? "目标对象",
              object:
                definition.roles?.[0]?.concept.ref ?? definition.target_type_id,
              kind: "object_type",
              parts: (join.source_columns ?? [join.source_column]).map((c) =>
                entry(c, [], undefined, src ? legacyDataset(src) : undefined),
              ),
            },
          ],
        });
      }
      if (definition.data_join && branches.length) {
        const join = definition.data_join;
        const columns =
          definition.endpoint_direction === "reverse"
            ? (join.target_columns ?? [join.target_column])
            : (join.source_columns ?? [join.source_column]);
        const sourceMapping = draft.mappings.find((m) => m.type_id === owner);
        const sourceTable = sourceMapping
          ? [sourceMapping.schema_name, sourceMapping.table_name]
              .filter(Boolean)
              .join(".")
          : undefined;
        const sourceDataset =
          datasets.find((d) => d.source === sourceTable) ??
          branches[0].source.find((e) => e.dataset)?.dataset;
        for (const branch of branches) {
          if (!branch.roles[0]) continue;
          branch.roles[0].parts = columns.map((column, i) => ({
            ...branch.roles[0].parts[i],
            value: column,
            expression: column,
            mode: "field",
            dataset: sourceDataset,
          }));
        }
      }
      return { definition, incoming, inherited, inheritedFrom, branches };
    },
  );
  const allTables = [
    mainDataset,
    ...properties.flatMap((p) =>
      p.entries.flatMap((e) => e.referencedDatasets ?? [e.dataset]),
    ),
  ].filter((d): d is SemanticDataset => !!d);
  const tables = [...new Map(allTables.map((d) => [d.id, d])).values()];
  const covered = properties.filter((p) =>
      p.entries.some(isMappedEntry),
    ).length,
    total = properties.length;
  const state =
    !keys.some(isMappedEntry) && !covered
      ? "unmapped"
      : covered < total
        ? "partial"
        : "mapped";
  return {
    object,
    properties,
    keys,
    mainDataset,
    tables,
    relations,
    models,
    mappings,
    usesLegacyForm: !!useLegacy,
    covered,
    total,
    state,
    label: { mapped: "已映射", partial: "部分映射", unmapped: "未映射" }[state],
  };
}
/** The API supplies READONLY_REASONS in its message; no client copy of the reason dictionary. */
export function readonlyReason(draft: LegacyDraft, id: string): string | null {
  const status = draft.mapping_status?.[id];
  if (!status?.reason) return null;
  const detail = status.message?.match(/[（(](.*)[）)]/)?.[1] ?? status.reason;
  return detail;
}
