import { MoreHorizontal, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { DataMapping, DataTable, SemanticDataset } from "../../api/types";
import { modelingApi, workspaceRequest } from "../../api/client";
import { isObject, VALUE_KINDS, type PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import {
  fullField,
  objectMapping,
  shortField,
  sourceColumns,
  type MappingEntry,
  type MappedProperty,
} from "../../lib/objectMapping";
import {
  propertyEntryChange,
  propertyReadonly,
  selectMappingDataset,
  stageMapping,
  tableReplacementReason,
} from "../../lib/objectMappingEditing";
import { ObjectTablePicker } from "./ObjectTablePicker";
import { IdentifierBar } from "./IdentifierBar";
import { FieldEditor, ReadonlyIcon } from "./MappingWidgets";

const typeGlyphs: Record<string, string> = {
  string: "ABC",
  integer: "123",
  decimal: "1.2",
  float: "1.2",
  boolean: "✓",
  date: "▦",
  datetime: "▦",
};
const sourceReason =
  "当前对象保存接口不能新增附表及关联字段、切换主表或移除原生来源表；请在「数据映射 › 语义模型 › 概念映射」中编辑来源表与连接。";
export function PropertyMappingTable(
  props: PanelProps & {
    suggestedSource?: Omit<
      DataMapping,
      "id" | "type_id" | "fields" | "key_column"
    >;
  },
) {
  const { draft, type, nativeDraft, editing, change } = props;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [selectedSource, setSelectedSource] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [preferred, setPreferred] = useState<SemanticDataset>();
  const [columns, setColumns] = useState<string[]>([]);
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  const connectionAlias = mapping?.connection_alias,
    tableName = mapping?.table_name,
    schemaName = mapping?.schema_name;
  useEffect(() => {
    let live = true;
    setColumns([]);
    if (!connectionAlias || !tableName) return;
    modelingApi
      .connections(draft.workspace_id)
      .then(async ({ items }) => {
        const connection = items.find((c) => c.name === connectionAlias);
        if (!connection) return;
        const response = await workspaceRequest<{ items: DataTable[] }>(
          draft.workspace_id,
          `/connections/${connection.id}/tables?table=${encodeURIComponent(tableName)}${schemaName ? "&schema_name=" + encodeURIComponent(schemaName) : ""}`,
        );
        if (live)
          setColumns(response.items[0]?.columns.map((c) => c.name) ?? []);
      })
      .catch(() => {
        if (live) setColumns([]);
      });
    return () => {
      live = false;
    };
  }, [draft.workspace_id, connectionAlias, tableName, schemaName]);
  if (!isObject(type)) return null;
  const record = objectMapping(draft, type, nativeDraft);
  const native =
    !!nativeDraft &&
    ((record.mappings.length > 0 && !record.usesLegacyForm) ||
      !!preferred ||
      !!draft._mapping_tables?.[type.id]);
  const mainSource = preferred ?? record.mainDataset;
  const main =
    !native && mainSource && columns.length
      ? {
          ...mainSource,
          fields: columns.map((name) => ({
            id: name,
            name,
            expression: {
              dialects: [{ dialect: "ANSI_SQL", expression: name }],
            },
          })),
        }
      : mainSource;
  const tables = [
    ...new Map(
      [main, ...record.tables]
        .filter((d): d is SemanticDataset => !!d)
        .map((d) => [d.id, d]),
    ).values(),
  ];
  const datasets = native ? tables : main ? [main] : [];
  const updateLegacy = (next: DataMapping) =>
    change({
      ...draft,
      _mapping_tables: {},
      mappings: [...draft.mappings.filter((m) => m.type_id !== type.id), next],
    });
  const update = (row: MappedProperty, index: number, entry: MappingEntry) => {
    if (native) propertyEntryChange(props, row.property, index, entry);
    else if (mapping) {
      const fields = { ...mapping.fields };
      if (entry.expression)
        fields[row.property.technical_name] = entry.expression;
      else delete fields[row.property.technical_name];
      updateLegacy({
        ...mapping,
        fields,
        ...(row.property.identifier ? { key_column: entry.expression } : {}),
      });
    }
  };
  const remove = (row: MappedProperty) => {
    let next = {
      ...draft,
      properties: draft.properties.filter((p) => p.id !== row.property.id),
      rules: draft.rules.filter(
        (r) => !(r.owner_kind === "property" && r.owner_id === row.property.id),
      ),
      mappings: draft.mappings.map((m) => {
        if (m.type_id !== type.id) return m;
        const fields = { ...m.fields };
        delete fields[row.property.technical_name];
        return { ...m, fields };
      }),
    };
    for (const cm of record.mappings) {
      const removed = new Set(
        cm.nodes
          .filter(
            (n) =>
              n.kind === "link" &&
              n.relationship === row.property.technical_name,
          )
          .map((n) => n.id),
      );
      let count = -1;
      while (count !== removed.size) {
        count = removed.size;
        cm.nodes.forEach((n) => {
          if (n.parent_id && removed.has(n.parent_id)) removed.add(n.id);
        });
      }
      if (removed.size)
        next = stageMapping(
          next,
          cm,
          cm.nodes.filter((n) => !removed.has(n.id)),
        );
    }
    change(next);
  };
  const add = () => {
    const id = newId();
    let number = 1;
    while (
      draft.properties.some(
        (p) =>
          p.owner_type_id === type.id &&
          p.technical_name === `property_${number}`,
      )
    )
      number++;
    change({
      ...draft,
      properties: [
        ...draft.properties,
        {
          id,
          owner_type_id: type.id,
          name: "",
          technical_name: `property_${number}`,
          description: "",
          value_kind: "string",
          identifier: false,
          required: false,
          evidence: [],
          verbalizes: [],
        },
      ],
    });
    setQuery("");
    setFilter("");
  };
  const rows = record.properties.filter(
    (row) =>
      `${row.property.name} ${row.property.technical_name}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (!filter ||
        (filter === "unbound"
          ? !row.entries.some((e) => e.expression && !e.pending)
          : row.entries.some((e) => e.dataset?.id === filter))),
  );
  const toolbar = (
    <div className="om-mapping-tools">
      <label className="om-search">
        <Search size={16} />
        <input
          aria-label="搜索属性"
          placeholder="搜索属性"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>
      <select
        aria-label="来源表"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      >
        <option value="">全部来源表</option>
        {tables.map((d) => (
          <option key={d.id} value={d.id} title={d.source}>
            {d.source.split(".").at(-1)}
          </option>
        ))}
        <option value="unbound">未绑定</option>
      </select>
    </div>
  );
  const grid = (
    <div className={editing ? "om-binding-grid" : ""}>
      {toolbar}
      <div className="om-table-wrap">
        <table
          className={`om-table om-properties${editing ? " om-properties--editing" : ""}`}
        >
          <thead>
            <tr>
              <th>属性</th>
              {editing ? (
                <>
                  <th>来源字段 ▾</th>
                  <th>类型 ▾</th>
                  <th>
                    <span className="sr-only">删除</span>
                  </th>
                </>
              ) : (
                <>
                  <th>类型</th>
                  <th>来源字段</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const property = row.property;
              const reason = row.inherited
                ? "继承属性的定义属于父对象，请编辑父对象。"
                : propertyReadonly(props, property);
              const derivation = draft.rules
                .filter(
                  (r) =>
                    r.owner_kind === "property" &&
                    r.owner_id === property.id &&
                    r.rule_kind === "derivation",
                )
                .map((r) => r.expression)
                .filter(Boolean)
                .join("\n");
              const derived =
                !!derivation ||
                row.entries.some((e) => e.mode === "expression");
              const entries: MappingEntry[] = row.entries.length
                ? row.entries
                : [
                    {
                      value: "",
                      expression: "",
                      mode: "field" as const,
                      dataset: main,
                    },
                  ];
              const typeCell = (
                <td data-label="类型">
                  {editing && !reason ? (
                    <select
                      aria-label={`${property.name}类型`}
                      value={property.value_kind}
                      onChange={(e) =>
                        change({
                          ...draft,
                          properties: draft.properties.map((p) =>
                            p.id === property.id
                              ? { ...p, value_kind: e.target.value }
                              : p,
                          ),
                        })
                      }
                    >
                      {Object.entries(VALUE_KINDS).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span>
                      <span className="om-type-glyph">
                        {typeGlyphs[property.value_kind] ?? "?"}
                      </span>
                      {VALUE_KINDS[property.value_kind] ?? "未知"}
                    </span>
                  )}
                </td>
              );
              const fields = (
                <td data-label="来源字段">
                  <div className="om-source-cell">
                    {entries.map((entry, index) => (
                      <div key={entry.nodeId ?? index} className="om-entry">
                        {editing && !reason ? (
                          native && entry.mode !== "field" ? (
                            <FieldEditor
                              entry={entry}
                              label={`${property.name} `}
                              onChange={(next) => update(row, index, next)}
                            />
                          ) : (
                            <>
                              <select
                                className="om-field-select"
                                aria-label={`${property.name} 字段`}
                                value={
                                  entry.expression && !entry.pending
                                    ? `${entry.dataset?.id ?? ""}|${entry.expression}`
                                    : ""
                                }
                                onChange={(e) => {
                                  const at = e.target.value.indexOf("|");
                                  const dataset = datasets.find(
                                    (d) => d.id === e.target.value.slice(0, at),
                                  );
                                  const expression =
                                    at < 0 ? "" : e.target.value.slice(at + 1);
                                  update(row, index, {
                                    ...entry,
                                    dataset,
                                    expression,
                                    mode: "field",
                                    pending: false,
                                  });
                                }}
                              >
                                <option value="">未绑定</option>
                                {datasets.map((dataset) => (
                                  <optgroup
                                    key={dataset.id}
                                    label={dataset.source.split(".").at(-1)}
                                  >
                                    {[
                                      ...new Set([
                                        ...sourceColumns(dataset),
                                        ...(entry.dataset?.id === dataset.id &&
                                        entry.expression &&
                                        !entry.pending
                                          ? [entry.expression]
                                          : []),
                                      ]),
                                    ].map((field) => (
                                      <option
                                        key={field}
                                        value={`${dataset.id}|${field}`}
                                        title={`${dataset.source}.${field}`}
                                      >
                                        {dataset.source.split(".").at(-1)}.
                                        {field}
                                      </option>
                                    ))}
                                  </optgroup>
                                ))}
                              </select>
                            </>
                          )
                        ) : !entry.expression || entry.pending ? (
                          <span className="muted">未绑定</span>
                        ) : (
                          <code title={fullField(entry)}>
                            {entry.mode === "constant"
                              ? entry.expression
                              : shortField(entry)}
                          </code>
                        )}
                        {entry.mode === "expression" && entry.expression && (
                          <code className="om-binding-expression">
                            {property.technical_name} = {entry.expression}
                          </code>
                        )}
                        {entry.mode === "constant" && (
                          <span className="om-tag">常量</span>
                        )}
                      </div>
                    ))}
                  </div>
                  {derivation && (
                    <code className="om-binding-expression">{derivation}</code>
                  )}
                  {editing && !native && (
                    <ReadonlyIcon reason="单表映射仅支持字段绑定；表达式、常量及多个来源请在「数据映射 › 语义模型 › 概念映射」中配置。" />
                  )}
                </td>
              );
              return (
                <tr key={property.id} data-element-id={property.id}>
                  <td data-label="属性">
                    <div className="om-property-name">
                      {editing && !row.inherited ? (
                        <input
                          aria-label={`${property.technical_name}属性名称`}
                          required
                          value={property.name}
                          onChange={(e) =>
                            change({
                              ...draft,
                              properties: draft.properties.map((p) =>
                                p.id === property.id
                                  ? { ...p, name: e.target.value }
                                  : p,
                              ),
                            })
                          }
                        />
                      ) : (
                        property.name
                      )}
                      {derived && <span className="om-tag">派生</span>}
                      {property.identifier && (
                        <span className="om-tag om-tag-key">标识</span>
                      )}
                      {row.inherited && <span className="om-tag">继承</span>}
                      {editing && <ReadonlyIcon reason={reason} />}
                    </div>
                    <code className="om-sub">{property.technical_name}</code>
                  </td>
                  {editing ? (
                    <>
                      {fields}
                      {typeCell}
                      <td>
                        <button
                          type="button"
                          className="icon-button"
                          aria-label={`删除${property.name}`}
                          disabled={!!reason || property.identifier}
                          onClick={() => remove(row)}
                        >
                          <Trash2 size={15} />
                        </button>
                        {property.identifier && (
                          <ReadonlyIcon reason="请先将实例标识改为其他属性，再删除此属性。" />
                        )}
                      </td>
                    </>
                  ) : (
                    <>
                      {typeCell}
                      {fields}
                    </>
                  )}
                </tr>
              );
            })}
            {!rows.length && (
              <tr>
                <td colSpan={editing ? 4 : 3} className="om-blank">
                  无匹配属性
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && (
        <div className="om-grid-actions">
          <button type="button" className="element-text-button" onClick={add}>
            ＋ 添加属性
          </button>
        </div>
      )}
    </div>
  );
  const replaceReason = tableReplacementReason(props);
  return (
    <>
      <IdentifierBar {...props} />
      <div className={editing ? "om-binding" : ""}>
        {editing && (
          <aside className="om-source-rail">
            <div className="om-section-head">
              <h3>数据来源</h3>
              <button
                type="button"
                className="element-text-button om-push"
                disabled={tables.length > 0 || !!replaceReason}
                onClick={() => setPicker(true)}
              >
                添加
              </button>
              <ReadonlyIcon
                reason={tables.length ? sourceReason : replaceReason}
              />
            </div>
            {tables.map((table) => {
              const primary = table.id === main?.id;
              const joins = record.models
                .flatMap((m) => m.relationships)
                .filter(
                  (j) =>
                    (j.from === main?.id && j.to === table.id) ||
                    (j.to === main?.id && j.from === table.id),
                );
              return (
                <div
                  className={`om-source-item${(selectedSource || main?.id) === table.id ? " is-active" : ""}`}
                  key={table.id}
                >
                  <div className="om-inline">
                    <button
                      type="button"
                      className="om-source-title"
                      title={table.source}
                      onClick={() => {
                        setSelectedSource(table.id);
                        setFilter(table.id);
                      }}
                    >
                      <code>{table.source.split(".").at(-1)}</code>
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`${table.source.split(".").at(-1)}菜单`}
                      aria-expanded={menu === table.id}
                      onClick={() =>
                        setMenu(menu === table.id ? null : table.id)
                      }
                    >
                      <MoreHorizontal size={16} />
                    </button>
                  </div>
                  {primary ? (
                    <span className="om-tag om-tag-key">主表</span>
                  ) : (
                    joins.map((join) => (
                      <code className="om-join-label" key={join.id}>
                        {join.from_columns
                          .map(
                            (column, i) => `${column} = ${join.to_columns[i]}`,
                          )
                          .join(" · ")}
                      </code>
                    ))
                  )}
                  {menu === table.id && (
                    <div className="om-source-menu" role="menu">
                      <div>
                        <button type="button" role="menuitem" disabled>
                          设为主表
                        </button>
                        <ReadonlyIcon reason={sourceReason} />
                      </div>
                      {!primary && (
                        <div>
                          <button type="button" role="menuitem" disabled>
                            关联字段
                          </button>
                          <ReadonlyIcon reason={sourceReason} />
                        </div>
                      )}
                      <div>
                        <button type="button" role="menuitem" disabled>
                          移除
                        </button>
                        <ReadonlyIcon reason={sourceReason} />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {!tables.length && <span className="muted">未绑定</span>}
          </aside>
        )}
        {grid}
      </div>
      {picker && (
        <ObjectTablePicker
          {...props}
          onClose={() => setPicker(false)}
          onDatasetSelected={(dataset) => {
            setPreferred(dataset);
            selectMappingDataset(props, dataset);
          }}
          onLegacySelected={(next) => {
            setPreferred(undefined);
            updateLegacy(next);
          }}
        />
      )}
    </>
  );
}
