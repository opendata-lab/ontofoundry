import { Alert, AutoComplete, Button, Checkbox, Descriptions, Empty, Form, Input, Segmented, Select, Table, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import { DetailWorkbench, SectionTitle } from "../layout";
import { Plus, Trash2, X } from "lucide-react";
import type { Draft, FieldBinding, ObjectType, Property, ValueKind } from "../../api/types";
import { VALUE_KINDS, byId, type ResolvedSource } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { bindingText, objectMapping, sourceColumns, sourceLabel, type MappedProperty } from "../../lib/objectMapping";
import { MAIN_SOURCE, identifierLockedReason, setFieldBinding } from "../../lib/objectMappingEditing";
import { upsert } from "../../lib/coreModel";
import { EvidenceSection } from "./ElementPanels";
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
    <div className="flex min-w-0 flex-col gap-3">
      <Segmented
        size="small"
        className="self-start"
        value={kind}
        onChange={(next) => next !== kind && onChange(next === "expression"
          ? { kind: "expression", expression: "" }
          : { kind: "column", source_id: sourceId, column: "" })}
        options={[{ value: "column", label: "列" }, { value: "expression", label: "计算" }]}
      />
      {kind === "column" ? (
        <div className="flex min-w-0 flex-col gap-2">
          {sources.length > 1 && (
            <Select
              size="small"
              aria-label={`${label}来源表`}
              className="w-full"
              value={sourceId}
              options={sources.map((s) => ({ value: s.id, label: sourceLabel(s, membership, shared) }))}
              onChange={(id: string) => onChange({ kind: "column", source_id: id, column: "" })}
            />
          )}
          <AutoComplete
            size="small"
            aria-label={`${label}列`}
            className="w-full"
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
          className="font-mono"
          autoSize={{ minRows: 3, maxRows: 8 }}
          placeholder={`例如 ${sources[0]?.id ?? MAIN_SOURCE}.first_name || ' ' || ${sources[0]?.id ?? MAIN_SOURCE}.last_name`}
          value={value?.kind === "expression" ? value.expression : ""}
          onChange={(e) => onChange({ kind: "expression", expression: e.target.value })}
        />
      )}
      {value && (
        <Button size="small" type="text" className="self-start" icon={<X size={14} />} aria-label={`解除${label}的绑定`} onClick={() => onChange(null)}>
          解除绑定
        </Button>
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

/** The list stays compact while the selected property's definition and binding share a detail pane. */
export function PropertiesPanel(props: PanelProps<ObjectType> & { initialPropertyId?: string }) {
  const { draft, type, editing, change, initialPropertyId } = props;
  const [selectedId, setSelectedId] = useState<string | null>(initialPropertyId ?? null);
  const [query, setQuery] = useState("");
  const record = objectMapping(draft, type);
  const lockedIdentifier = identifierLockedReason(draft, type.id);
  const rows = record.properties.filter(({ property }) =>
    `${property.name} ${property.technical_name}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selected = rows.find((row) => row.property.id === selectedId) ?? rows[0];
  const property = selected?.property;
  const own = selected && !selected.inheritedFrom;
  const editable = editing && own;
  const setProperty = (value: Property, patch: Partial<Property>) =>
    change({ ...draft, properties: draft.properties.map((p) => p.id === value.id ? { ...p, ...patch } : p) });
  const bindingReason = (row: MappedProperty): string | null => {
    if (record.properties.filter((other) => other.property.technical_name === row.property.technical_name).length > 1)
      return "英文标识重复，请先完成改名";
    if (record.mode === "virtual" || (record.mode === "unbound" && !record.mapping)) return "先在上方选择数据集";
    if (record.mode === "shared_parent" && row.inheritedFrom) return "继承属性使用父对象的数据绑定";
    return null;
  };
  const reason = selected ? bindingReason(selected) : null;
  const addProperty = () => {
    const id = newId();
    setQuery("");
    setSelectedId(id);
    change({ ...draft, properties: [...draft.properties, {
      id, owner_type_id: type.id, name: "", technical_name: "", description: "", synonyms: [], evidence: [],
      value_kind: "string", identifier: false, unique: false, required: false,
    }] });
  };
  const constraints = (value: Property) => <span className="inline-flex flex-wrap gap-1">
    {value.identifier && <Tooltip title="业务上识别实例的属性；多个标识属性共同组成业务标识，例如订单号＋行号"><Tag className="m-0 border-accent bg-accent-soft text-accent">标识</Tag></Tooltip>}
    {value.unique && <Tooltip title="该属性值在同类对象实例中唯一"><Tag className="m-0">唯一</Tag></Tooltip>}
    {value.required && <Tooltip title="该属性为必填业务信息"><Tag className="m-0">必填</Tag></Tooltip>}
    {!value.identifier && !value.unique && !value.required && <Text type="secondary">—</Text>}
  </span>;
  const flag = (field: "identifier" | "unique" | "required", label: string) => property && (
    <Checkbox
      aria-label={`${property.name || "属性"}${field === "identifier" ? "是标识" : label}`}
      checked={property[field]}
      disabled={!editable || (field === "identifier" && !!lockedIdentifier) || undefined}
      onChange={(e) => setProperty(property, { [field]: e.target.checked })}
    >{label}</Checkbox>
  );
  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-3 border-b border-rule pb-4">
        <SectionTitle title="数据来源" />
        <MappingSources draft={draft} type={type} editing={editing} change={change} />
      </section>
      <DetailWorkbench detailLabel="选中属性配置" primary={
        <>
          <SectionTitle title="属性" note={`${record.properties.length} 个`}>
            {editing && <Button size="small" icon={<Plus size={14} />} onClick={addProperty}>添加属性</Button>}
          </SectionTitle>
          <Input size="small" type="search" aria-label="搜索属性" placeholder="搜索名称或英文标识" allowClear value={query} onChange={(e) => setQuery(e.target.value)} />
          <Table<MappedProperty>
            size="small"
            rowKey={(row) => row.property.id}
            pagination={false}
            dataSource={rows}
            onRow={(row) => ({ onClick: () => setSelectedId(row.property.id), className: row.property.id === property?.id ? "inspector-selection-row cursor-pointer" : "cursor-pointer" })}
            locale={{ emptyText: <Empty description={query ? "没有匹配的属性" : "尚未定义属性"} /> }}
            columns={[
              { title: "属性", key: "name", render: (_, row) => (
                <div className="flex min-w-0 flex-col" data-element-id={row.property.id}>
                  <span className="font-medium">{row.property.name || "未命名属性"}</span>
                  <code className="text-xs text-muted">{row.property.technical_name || "尚未设置英文标识"}</code>
                  {row.inheritedFrom && <Text type="secondary" className="text-xs">继承自{byId(draft.object_types, row.inheritedFrom)?.name}</Text>}
                </div>
              ) },
              { title: "类型", key: "kind", render: (_, row) => VALUE_KINDS[row.property.value_kind] },
              { title: "约束", key: "constraints", render: (_, row) => constraints(row.property) },
            ]}
          />
        </>
      } detail={
        <>
          {property && selected ? (
            <>
              {selected.inheritedFrom && <Text type="secondary">继承自{byId(draft.object_types, selected.inheritedFrom)?.name}，属性定义在所属对象上修改。</Text>}
              <section className="flex flex-col gap-3">
                <SectionTitle title="基本信息">
                  {editable && <Button danger type="text" size="small" aria-label={`删除属性 ${property.name}`} icon={<Trash2 size={14} />} onClick={() => change(deleteProperty(draft, type, property))}>删除</Button>}
                </SectionTitle>
                {editable ? (
                  <Form layout="vertical" component="div" size="small">
                    <Form.Item className="mb-3" label="名称" required><Input aria-label="属性名称" value={property.name} onChange={(e) => setProperty(property, { name: e.target.value })} /></Form.Item>
                    <Form.Item className="mb-3" label="英文标识" required><Input aria-label="属性英文标识" className="font-mono" value={property.technical_name} onChange={(e) => change(renameProperty(draft, property, e.target.value.trim()))} /></Form.Item>
                    <Form.Item className="mb-3" label="类型"><Select aria-label={`${property.name || "属性"}类型`} className="w-full" value={property.value_kind} options={Object.entries(VALUE_KINDS).map(([value, label]) => ({ value, label }))} onChange={(value_kind: ValueKind) => setProperty(property, { value_kind })} /></Form.Item>
                    <Form.Item label="描述" className="mb-0"><Input.TextArea aria-label={`${property.name || "属性"}描述`} autoSize={{ minRows: 2, maxRows: 6 }} value={property.description} onChange={(e) => setProperty(property, { description: e.target.value })} /></Form.Item>
                  </Form>
                ) : <Descriptions size="small" column={1} items={[
                  { key: "name", label: "名称", children: property.name || "未命名属性" },
                  { key: "technical", label: "英文标识", children: <code>{property.technical_name || "—"}</code> },
                  { key: "kind", label: "类型", children: VALUE_KINDS[property.value_kind] },
                  { key: "description", label: "描述", children: property.description || <Text type="secondary">暂无描述</Text> },
                ]} />}
              </section>
              <section className="flex flex-col gap-3 border-t border-rule pt-4">
                <SectionTitle title="约束" />
                {editing ? <div className="flex flex-wrap gap-3">{flag("identifier", "标识")}{flag("unique", "唯一")}{flag("required", "必填")}</div> : <Text>{constraints(property)}</Text>}
                {editing && lockedIdentifier && <Text type="secondary" className="text-xs">{lockedIdentifier}</Text>}
              </section>
              <section className="flex flex-col gap-3 border-t border-rule pt-4">
                <SectionTitle title="数据绑定" />
                {editing && !reason ? <BindingEditor label={property.name || property.technical_name} value={selected.boundBy === type.id ? selected.binding : undefined} sources={record.sources} membership={record.mapping?.membership_source_id ?? null} shared={record.mode === "shared_parent"} onChange={(binding) => change(setFieldBinding(draft, type.id, property, binding))} /> : (
                  <>
                    {selected.binding ? <code className="whitespace-pre-wrap break-words text-xs">{bindingText(selected.binding)}</code> : <Text type="secondary">未绑定</Text>}
                    {selected.boundBy && selected.boundBy !== type.id && <Text type="secondary">来自{byId(draft.object_types, selected.boundBy)?.name}</Text>}
                    {editing && reason && <Alert type="info" showIcon message={reason} />}
                  </>
                )}
              </section>
              <EvidenceSection workspaceId={draft.workspace_id} evidence={property.evidence} />
            </>
          ) : <Empty description="选择属性查看定义与数据绑定" />}
        </>
      } />
    </div>
  );
}
