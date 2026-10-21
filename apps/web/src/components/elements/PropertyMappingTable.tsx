import { Alert, AutoComplete, Button, Checkbox, Empty, Input, Select, Table, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import { ContentBlock, SectionTitle, SourceFieldsLayout } from "../layout";
import { CircleHelp, Plus, Trash2 } from "lucide-react";
import type { Draft, FieldBinding, ObjectType, Property, ValueKind } from "../../api/types";
import { VALUE_KINDS, byId, type ResolvedSource } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { valueTypeRules } from "../../lib/valueTypes";
import { bindingText, objectMapping, sourceColumns, sourceLabel, type MappedProperty } from "../../lib/objectMapping";
import { MAIN_SOURCE, identifierLockedReason, setFieldBinding } from "../../lib/objectMappingEditing";
import { upsert } from "../../lib/coreModel";
import { EvidenceSection, ValueTypeSourceLink } from "./ElementPanels";
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
  const [emptyKind, setEmptyKind] = useState<"column" | "expression">(value?.kind ?? "column");
  const kind = value?.kind ?? emptyKind;
  const sourceId = value?.kind === "column" ? value.source_id : (sources[0]?.id ?? MAIN_SOURCE);
  const source = sources.find((s) => s.id === sourceId);
  return (
    <div className="flex min-w-0 items-start gap-1">
      <Select
        size="small"
        className="w-binding-mode shrink-0"
        aria-label={`${label}绑定方式`}
        value={kind}
        onChange={(next) => {
          setEmptyKind(next === "expression" ? "expression" : "column");
          if (next !== kind) onChange(next === "expression"
            ? { kind: "expression", expression: "" }
            : { kind: "column", source_id: sourceId, column: "" });
        }}
        options={[{ value: "column", label: "列" }, { value: "expression", label: "计算" }]}
      />
      {kind === "column" ? (
        <div className="flex min-w-0 flex-1 items-center gap-1">
          {sources.length > 1 && (
            <Select
              size="small"
              aria-label={`${label}来源表`}
              className="w-binding-source shrink-0"
              value={sourceId}
              options={sources.map((s) => ({ value: s.id, label: sourceLabel(s, membership, shared) }))}
              onChange={(id: string) => onChange({ kind: "column", source_id: id, column: "" })}
            />
          )}
          <AutoComplete
            size="small"
            aria-label={`${label}列`}
            allowClear
            className="min-w-0 flex-1"
            placeholder="选择或输入列名"
            value={value?.kind === "column" ? value.column : ""}
            options={sourceColumns(source?.dataset).map((c) => ({ value: c }))}
            filterOption={(input, option) => String(option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
            onChange={(column: string) => onChange(column ? { kind: "column", source_id: sourceId, column } : null)}
          />
        </div>
      ) : (
        <Input.TextArea
          size="small"
          aria-label={`${label}计算表达式`}
          allowClear
          className="min-w-0 flex-1 font-mono"
          autoSize={{ minRows: 1, maxRows: 6 }}
          placeholder={`例如 ${sources[0]?.id ?? MAIN_SOURCE}.first_name || ' ' || ${sources[0]?.id ?? MAIN_SOURCE}.last_name`}
          value={value?.kind === "expression" ? value.expression : ""}
          onChange={(e) => onChange(e.target.value ? { kind: "expression", expression: e.target.value } : null)}
        />
      )}

    </div>
  );
}

function renameProperty(draft: Draft, property: Property, technical: string): Draft {
  return {
    ...draft,
    properties: draft.properties.map((p) => (p.id === property.id ? { ...p, name: technical } : p)),
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
  if (!mapping?.fields[property.name]) return next;
  const fields = { ...mapping.fields };
  delete fields[property.name];
  return upsert(next, "mappings", { ...mapping, fields });
}

/** Definitions and bindings share a row so properties can be compared and edited together. */
export function PropertiesPanel(props: PanelProps<ObjectType> & { initialPropertyId?: string }) {
  const { draft, type, editing, change } = props;
  const [query, setQuery] = useState("");
  const record = objectMapping(draft, type);
  const lockedIdentifier = identifierLockedReason(draft, type.id);
  const rows = record.properties.filter(({ property }) =>
    `${(property.display_name || property.name)} ${property.name}`.toLowerCase().includes(query.trim().toLowerCase()));
  const setProperty = (value: Property, patch: Partial<Property>) =>
    change({ ...draft, properties: draft.properties.map((p) => p.id === value.id ? { ...p, ...patch } : p) });
  const bindingReason = (row: MappedProperty): string | null => {
    if (record.properties.filter((other) => other.property.name === row.property.name).length > 1)
      return "英文标识重复，请先完成改名";
    if (record.mode === "virtual" || (record.mode === "unbound" && !record.mapping)) return "先在上方选择数据集";
    if (record.mode === "shared_parent" && row.inheritedFrom) return "继承属性使用父对象的数据绑定";
    return null;
  };
  const addProperty = () => {
    const id = newId();
    setQuery("");
    change({ ...draft, properties: [...draft.properties, {
      id, owner_type_id: type.id, display_name: "", name: "", description: "", synonyms: [], evidence: [], value_type_id: null,
      value_kind: "string", identifier: false, unique: false, required: false,
    }] });
  };
  const constraints = (value: Property) => <span className="inline-flex flex-wrap gap-1">
    {value.identifier && <Tooltip title="业务上识别实例的属性；多个标识属性共同组成业务标识，例如订单号＋行号"><Tag className="m-0 border-accent bg-accent-soft text-accent">标识</Tag></Tooltip>}
    {value.unique && <Tooltip title="该属性值在同类对象实例中唯一"><Tag className="m-0">唯一</Tag></Tooltip>}
    {value.required && <Tooltip title="该属性为必填业务信息"><Tag className="m-0">必填</Tag></Tooltip>}
    {!value.identifier && !value.unique && !value.required && <Text type="secondary">—</Text>}
  </span>;
  const flag = (row: MappedProperty, field: "identifier" | "unique" | "required", label: string) => (
    <Checkbox
      aria-label={`${row.property.display_name || row.property.name || "属性"}${field === "identifier" ? "是标识" : label}`}
      checked={row.property[field]}
      disabled={!!row.inheritedFrom || (field === "identifier" && !!lockedIdentifier) || undefined}
      onChange={(event) => setProperty(row.property, { [field]: event.target.checked })}
    >{label}</Checkbox>
  );
  return (
    <SourceFieldsLayout source={
      <ContentBlock className="source-fields-source">
        <SectionTitle title="数据来源" note={editing ? <Tooltip title="选择可唯一识别记录的列；组合键按顺序选择，附表键与主表逐列对应。快照表按同一快照时点识别。"><Button type="text" size="small" aria-label="数据来源绑定说明" icon={<CircleHelp size={14} />} /></Tooltip> : undefined} />
        <MappingSources draft={draft} type={type} editing={editing} change={change} />
      </ContentBlock>
    } fields={
      <ContentBlock>
        <SectionTitle title="字段" note={`${record.properties.length} 个`}>
          {editing && <Button size="small" icon={<Plus size={14} />} onClick={addProperty}>添加属性</Button>}
        </SectionTitle>
        <Input className="w-inspector-search max-w-full" size="small" type="search" aria-label="搜索属性" placeholder="搜索名称或英文标识" allowClear value={query} onChange={(event) => setQuery(event.target.value)} />
        {editing && lockedIdentifier && <Alert type="info" showIcon message={lockedIdentifier} />}
        <Table<MappedProperty>
          size="small"
          rowKey={(row) => row.property.id}
          pagination={false}
          dataSource={rows}
          tableLayout="fixed"
          scroll={{ x: "var(--property-table-min-width)" }}
          expandable={rows.some((row) => row.property.evidence.length > 0) ? {
            rowExpandable: (row) => row.property.evidence.length > 0,
            expandedRowRender: (row) => <EvidenceSection workspaceId={draft.workspace_id} evidence={row.property.evidence} />,
          } : undefined}
          locale={{ emptyText: <Empty description={query ? "没有匹配的属性" : "尚未定义属性"} /> }}
          columns={[
            { title: "名称", key: "name", fixed: "left", width: "var(--property-name-column)", render: (_, row) => (
              <div className="flex min-w-0 flex-col gap-1" data-element-id={row.property.id}>
                {editing && !row.inheritedFrom ? <Input size="small" aria-label="属性名称" placeholder="名称" value={row.property.display_name ?? ""} onChange={(event) => setProperty(row.property, { display_name: event.target.value })} /> : <span className="font-medium">{row.property.display_name || row.property.name || "未命名属性"}</span>}
                {row.inheritedFrom && <Text type="secondary" className="text-xs">继承自{byId(draft.object_types, row.inheritedFrom)?.display_name || byId(draft.object_types, row.inheritedFrom)?.name}</Text>}
              </div>
            ) },
            { title: "英文标识", key: "technical", width: "var(--property-technical-column)", render: (_, row) => editing && !row.inheritedFrom ? <Input size="small" aria-label="属性英文标识" placeholder="英文标识" className="font-mono" value={row.property.name} onChange={(event) => change(renameProperty(draft, row.property, event.target.value.trim()))} /> : <code className="text-xs text-muted">{row.property.name || "—"}</code> },
            { title: "类型", key: "kind", width: "var(--property-kind-column)", render: (_, row) => editing && !row.inheritedFrom ? (
              <Select size="small" aria-label={`${row.property.display_name || row.property.name || "属性"}类型`} className="w-full" value={row.property.value_type_id ? `vt:${row.property.value_type_id}` : `kind:${row.property.value_kind}`}
                options={[
                  { label: "内置类型", options: Object.entries(VALUE_KINDS).map(([value, label]) => ({ value: `kind:${value}`, label })) },
                  ...((draft.value_types ?? []).length ? [{ label: "值类型", options: (draft.value_types ?? []).map((value) => ({ value: `vt:${value.id}`, label: `${value.display_name || value.name}（${VALUE_KINDS[value.value_kind]}）` })) }] : []),
                ]}
                onChange={(choice: string) => {
                  const [mode, key] = choice.split(":");
                  const shared = mode === "vt" ? byId(draft.value_types ?? [], key) : undefined;
                  setProperty(row.property, shared ? { value_type_id: shared.id, value_kind: shared.value_kind } : { value_type_id: null, value_kind: key as ValueKind });
                }} />
            ) : typeLabel(draft, row.property) },
            { title: "约束", key: "constraints", width: "var(--property-constraints-column)", render: (_, row) => <div className="flex flex-col gap-2">
              {editing ? <div className="flex flex-wrap items-center gap-1">{flag(row, "identifier", "标识")}{flag(row, "unique", "唯一")}{flag(row, "required", "必填")}</div> : constraints(row.property)}
              <InheritedValueConstraints draft={draft} property={row.property} />
            </div> },
            { title: "数据绑定", key: "binding", width: "var(--property-binding-column)", render: (_, row) => {
              const reason = bindingReason(row);
              return editing && !reason ? <BindingEditor label={row.property.display_name || row.property.name || "属性"} value={row.boundBy === type.id ? row.binding : undefined} sources={record.sources} membership={record.mapping?.membership_source_id ?? null} shared={record.mode === "shared_parent"} onChange={(binding) => change(setFieldBinding(draft, type.id, row.property, binding))} /> : <div className="flex flex-col gap-1">
                {row.binding ? <code className="whitespace-pre-wrap break-words text-xs">{bindingText(row.binding)}</code> : <Text type="secondary">未绑定</Text>}
                {row.boundBy && row.boundBy !== type.id && <Text type="secondary">来自{byId(draft.object_types, row.boundBy)?.display_name || byId(draft.object_types, row.boundBy)?.name}</Text>}
                {editing && reason && !row.inheritedFrom && <Text type="secondary" className="text-xs">{reason}</Text>}
              </div>;
            } },
            { title: "描述", key: "description", render: (_, row) => editing && !row.inheritedFrom ? <Input.TextArea size="small" aria-label={`${row.property.display_name || row.property.name || "属性"}描述`} autoSize={{ minRows: 1, maxRows: 6 }} value={row.property.description} onChange={(event) => setProperty(row.property, { description: event.target.value })} /> : <Text className="block max-w-property-binding whitespace-normal" type={row.property.description ? undefined : "secondary"}>{row.property.description || "—"}</Text> },
            ...(editing ? [{ title: "操作", key: "actions", fixed: "right" as const, width: "var(--property-actions-column)", render: (_: unknown, row: MappedProperty) => !row.inheritedFrom && <Button danger type="text" size="small" aria-label={`删除属性 ${row.property.display_name || row.property.name}`} icon={<Trash2 size={14} />} onClick={() => change(deleteProperty(draft, type, row.property))} /> }] : []),
          ]}
        />
      </ContentBlock>
    } />
  );
}

/** Built-in kind, or the shared value type with its base kind. */
function typeLabel(draft: Draft, property: Property) {
  const shared = property.value_type_id ? byId(draft.value_types ?? [], property.value_type_id) : undefined;
  return shared ? `${shared.display_name || shared.name}（值类型 · ${VALUE_KINDS[shared.value_kind]}）` : VALUE_KINDS[property.value_kind];
}

/** Constraints inherited from the value type: shown greyed and read-only (VT-10). */
function InheritedValueConstraints({ draft, property }: { draft: Draft; property: Property }) {
  const shared = property.value_type_id ? byId(draft.value_types ?? [], property.value_type_id) : undefined;
  if (!shared) return null;
  const rules = valueTypeRules(draft, shared.id);
  if (!rules.length) return null;
  return (
    <ul className="m-0 flex list-none flex-col gap-1 p-0" aria-label="继承自值类型的约束">
      {rules.map((r) => (
        <li key={r.id} className="flex flex-wrap items-center gap-2 text-muted">
          <code className="text-xs">{r.expression}</code>
          <Text type="secondary" className="text-xs">继承自<ValueTypeSourceLink workspaceId={draft.workspace_id} name={shared.display_name || shared.name} />，只读</Text>
        </li>
      ))}
    </ul>
  );
}
