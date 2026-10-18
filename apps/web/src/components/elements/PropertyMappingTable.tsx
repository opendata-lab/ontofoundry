import { AutoComplete, Button, Checkbox, Input, Segmented, Select, Table, Tag, Tooltip, Typography } from "antd";
import { Plus, Trash2, X } from "lucide-react";
import type { Draft, FieldBinding, ObjectType, Property, ValueKind } from "../../api/types";
import { VALUE_KINDS, byId, type ResolvedSource } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { bindingText, objectMapping, sourceColumns, sourceLabel, type MappedProperty } from "../../lib/objectMapping";
import { MAIN_SOURCE, identifierLockedReason, setFieldBinding } from "../../lib/objectMappingEditing";
import { upsert } from "../../lib/coreModel";
import { ReadonlyIcon } from "./MappingWidgets";
import { MappingSources } from "./ObjectTablePicker";

const { Text } = Typography;

function BindingEditor({
  label,
  value,
  sources,
  membership,
  shared,
  onChange,
}: {
  label: string;
  value: FieldBinding | undefined;
  sources: ResolvedSource[];
  membership: string | null;
  shared: boolean;
  onChange: (binding: FieldBinding | null) => void;
}) {
  const kind = value?.kind ?? "column";
  const sourceId = value?.kind === "column" ? value.source_id : (sources[0]?.id ?? MAIN_SOURCE);
  const source = sources.find((s) => s.id === sourceId);
  return (
    <div className="flex min-w-[300px] items-center gap-1">
      <Segmented
        size="small"
        value={kind}
        onChange={(next) =>
          next !== kind &&
          onChange(next === "expression" ? { kind: "expression", expression: "" } : { kind: "column", source_id: sourceId, column: "" })
        }
        options={[
          { value: "column", label: "列" },
          { value: "expression", label: "计算" },
        ]}
      />
      {kind === "column" ? (
        <>
          {sources.length > 1 && (
            <Select
              size="small"
              aria-label={`${label}来源表`}
              className="w-[96px]"
              value={sourceId}
              options={sources.map((s) => ({ value: s.id, label: sourceLabel(s, membership, shared) }))}
              onChange={(id: string) => onChange({ kind: "column", source_id: id, column: "" })}
            />
          )}
          <AutoComplete
            size="small"
            aria-label={`${label}列`}
            className="min-w-[140px] flex-1"
            placeholder="选择或输入列名"
            value={value?.kind === "column" ? value.column : ""}
            options={sourceColumns(source?.dataset).map((c) => ({ value: c }))}
            filterOption={(input, option) => String(option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
            onChange={(column: string) =>
              onChange(column ? { kind: "column", source_id: sourceId, column } : null)
            }
          />
        </>
      ) : (
        <Input
          size="small"
          aria-label={`${label}计算表达式`}
          className="flex-1 font-mono"
          placeholder={`例如 ${sources[0]?.id ?? MAIN_SOURCE}.first_name || ' ' || ${sources[0]?.id ?? MAIN_SOURCE}.last_name`}
          value={value?.kind === "expression" ? value.expression : ""}
          onChange={(e) => onChange({ kind: "expression", expression: e.target.value })}
        />
      )}
      {value && (
        <Tooltip title="解除绑定">
          <Button size="small" type="text" aria-label={`解除${label}的绑定`} icon={<X size={14} />} onClick={() => onChange(null)} />
        </Tooltip>
      )}
    </div>
  );
}

function renameProperty(draft: Draft, property: Property, technical: string): Draft {
  return {
    ...draft,
    properties: draft.properties.map((p) => (p.id === property.id ? { ...p, technical_name: technical } : p)),
  };
}

function deleteProperty(draft: Draft, type: ObjectType, property: Property): Draft {
  const next: Draft = {
    ...draft,
    properties: draft.properties.filter((p) => p.id !== property.id),
    rules: draft.rules.filter((r) => !(r.owner_kind === "property" && r.owner_id === property.id)),
    object_types: draft.object_types.map((o) =>
      o.id === type.id && o.title_property_id === property.id ? { ...o, title_property_id: null } : o,
    ),
  };
  const mapping = next.mappings.find((m) => m.type_id === type.id);
  if (!mapping?.fields[property.technical_name]) return next;
  const fields = { ...mapping.fields };
  delete fields[property.technical_name];
  return upsert(next, "mappings", { ...mapping, fields });
}

/** Properties of the object (own and inherited) and how each is bound to data. */
export function PropertiesPanel(props: PanelProps<ObjectType>) {
  const { draft, type, editing, change } = props;
  const record = objectMapping(draft, type);
  const lockedIdentifier = identifierLockedReason(draft, type.id);
  const setProperty = (property: Property, patch: Partial<Property>) =>
    change({ ...draft, properties: draft.properties.map((p) => (p.id === property.id ? { ...p, ...patch } : p)) });
  // A shared child binds only its own properties; inherited ones come from the parent's mapping.
  const bindingReason = (row: MappedProperty): string | null => {
    if (record.properties.filter((other) => other.property.technical_name === row.property.technical_name).length > 1)
      return "技术名重复，请先完成改名";
    if (record.mode === "virtual" || (record.mode === "unbound" && !record.mapping))
      return "先在上方选择数据集";
    if (record.mode === "shared_parent" && row.inheritedFrom) return "继承属性使用父对象的数据绑定";
    return null;
  };
  const addProperty = () =>
    change({
      ...draft,
      properties: [
        ...draft.properties,
        {
          id: newId(),
          owner_type_id: type.id,
          name: "",
          technical_name: "",
          description: "",
          synonyms: [],
          evidence: [],
          value_kind: "string",
          identifier: false,
          unique: false,
          required: false,
        },
      ],
    });
  const own = (row: MappedProperty) => !row.inheritedFrom;
  const flag = (row: MappedProperty, field: "identifier" | "unique" | "required", label: string) => {
    const locked = field === "identifier" && lockedIdentifier;
    const editable = editing && own(row) && !locked;
    return (
      <Checkbox
        aria-label={`${row.property.name || "属性"}${label}`}
        checked={row.property[field]}
        disabled={!editable || undefined}
        onChange={(e) => setProperty(row.property, { [field]: e.target.checked })}
      />
    );
  };
  const identifierCount = record.properties.filter((p) => p.property.identifier).length;
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-2">
        <Text strong>数据来源</Text>
        <MappingSources draft={draft} type={type} editing={editing} change={change} />
      </section>
      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <Text strong>属性</Text>
          <Text type="secondary" className="text-xs">
            {identifierCount > 1 ? "多个属性组成复合标识" : "标识用于定位唯一实例"}
            {lockedIdentifier ? `；${lockedIdentifier}` : ""}
          </Text>
        </div>
        <Table
          size="small"
          rowKey={(row) => row.property.id}
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={record.properties}
          columns={[
            {
              title: "属性",
              key: "name",
              fixed: "left",
              width: 220,
              render: (_, row) =>
                editing && own(row) ? (
                  <div className="flex flex-col gap-1" data-element-id={row.property.id}>
                    <Input
                      size="small"
                      aria-label="属性名称"
                      placeholder="名称"
                      value={row.property.name}
                      onChange={(e) => setProperty(row.property, { name: e.target.value })}
                    />
                    <Input
                      size="small"
                      aria-label="属性技术名"
                      placeholder="技术名"
                      className="font-mono"
                      value={row.property.technical_name}
                      onChange={(e) => change(renameProperty(draft, row.property, e.target.value.trim()))}
                    />
                  </div>
                ) : (
                  <div className="flex flex-col" data-element-id={row.property.id}>
                    <span>{row.property.name}</span>
                    <code className="text-xs text-muted">{row.property.technical_name}</code>
                    {row.inheritedFrom && (
                      <Text type="secondary" className="text-xs">
                        继承自{byId(draft.object_types, row.inheritedFrom)?.name}
                      </Text>
                    )}
                  </div>
                ),
            },
            {
              title: "类型",
              key: "kind",
              width: 110,
              render: (_, row) =>
                editing && own(row) ? (
                  <Select
                    size="small"
                    aria-label={`${row.property.name || "属性"}类型`}
                    className="w-full"
                    value={row.property.value_kind}
                    options={Object.entries(VALUE_KINDS).map(([value, label]) => ({ value, label }))}
                    onChange={(value_kind: ValueKind) => setProperty(row.property, { value_kind })}
                  />
                ) : (
                  VALUE_KINDS[row.property.value_kind]
                ),
            },
            { title: "标识", key: "identifier", width: 56, align: "center", render: (_, row) => flag(row, "identifier", "是标识") },
            { title: "唯一", key: "unique", width: 56, align: "center", render: (_, row) => flag(row, "unique", "唯一") },
            { title: "必填", key: "required", width: 56, align: "center", render: (_, row) => flag(row, "required", "必填") },
            {
              title: "数据绑定",
              key: "binding",
              render: (_, row) => {
                const reason = bindingReason(row);
                if (editing && !reason)
                  return (
                    <BindingEditor
                      label={row.property.name || row.property.technical_name}
                      value={row.boundBy === type.id ? row.binding : undefined}
                      sources={record.sources}
                      membership={record.mapping?.membership_source_id ?? null}
                      shared={record.mode === "shared_parent"}
                      onChange={(binding) => change(setFieldBinding(draft, type.id, row.property, binding))}
                    />
                  );
                return (
                  <span className="flex items-center gap-2">
                    {row.binding ? <code className="text-xs">{bindingText(row.binding)}</code> : <Text type="secondary">未绑定</Text>}
                    {row.binding?.kind === "expression" && <Tag className="!m-0">计算</Tag>}
                    {row.boundBy && row.boundBy !== type.id && (
                      <Text type="secondary" className="text-xs">
                        来自{byId(draft.object_types, row.boundBy)?.name}
                      </Text>
                    )}
                    {editing && <ReadonlyIcon reason={reason} />}
                  </span>
                );
              },
            },
            {
              title: "描述",
              key: "description",
              width: 220,
              render: (_, row) =>
                editing && own(row) ? (
                  <Input.TextArea
                    size="small"
                    aria-label={`${row.property.name || "属性"}描述`}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    value={row.property.description}
                    onChange={(e) => setProperty(row.property, { description: e.target.value })}
                  />
                ) : (
                  <Text type="secondary" className="text-xs">
                    {row.property.description}
                  </Text>
                ),
            },
            ...(editing
              ? [
                  {
                    title: "",
                    key: "actions",
                    width: 40,
                    render: (_: unknown, row: MappedProperty) =>
                      own(row) ? (
                        <Button
                          type="text"
                          size="small"
                          aria-label={`删除属性 ${row.property.name}`}
                          icon={<Trash2 size={14} />}
                          onClick={() => change(deleteProperty(draft, type, row.property))}
                        />
                      ) : null,
                  },
                ]
              : []),
          ]}
        />
        {editing && (
          <Button type="dashed" icon={<Plus size={15} />} className="self-start" onClick={addProperty}>
            添加属性
          </Button>
        )}
      </section>
    </div>
  );
}
