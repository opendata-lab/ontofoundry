import { Button, Descriptions, Empty, Form, Input, Select, Table, Tag, TreeSelect, Typography } from "antd";
import { FileText, Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import type { Draft, Evidence, LinkType, ObjectType, Rule } from "../../api/types";
import {
  MULTIPLICITY,
  byId,
  children,
  effectiveProperties,
  identifier,
  joinSummary,
  lineage,
  mappingFor,
  remove,
  titleProperty,
  upsert,
} from "../../lib/coreModel";
import { changeType, objectTree, rulesFor, type PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { BINDING_MODES, objectMapping } from "../../lib/objectMapping";
import { DerivedConditionEditor, DerivedSummary } from "./DerivedConditionEditor";
import { MappingStatusIcon } from "./MappingWidgets";
import { ObjectRelationGraph } from "./ObjectRelationGraph";

const { Text, Paragraph } = Typography;

export function EvidenceSection({ workspaceId, evidence }: { workspaceId: string; evidence: Evidence[] }) {
  if (!evidence.length) return null;
  return (
    <section className="flex flex-col gap-2">
      <Text strong>来源证据</Text>
      {evidence.map((ev) => (
        <div key={ev.id} className="flex flex-col gap-1 rounded-sm bg-surface-soft px-3 py-2 text-sm">
          {"material_id" in ev ? (
            <>
              <a
                className="inline-flex items-center gap-1"
                href={`/api/v1/workspaces/${workspaceId}/materials/${encodeURIComponent(ev.material_id)}`}
                target="_blank"
                rel="noreferrer"
              >
                <FileText size={15} />
                查看来源材料 · 第 {ev.locator.line_start}–{ev.locator.line_end} 行
              </a>
              {ev.quote && <Text type="secondary">“{ev.quote}”</Text>}
            </>
          ) : (
            <span className="inline-flex items-center gap-1">
              <FileText size={15} />
              人工确认{ev.note ? `：${ev.note}` : ""}
            </span>
          )}
        </div>
      ))}
    </section>
  );
}

export function TagsText({ items }: { items: string[] }) {
  return items.length ? (
    <span className="flex flex-wrap gap-1">
      {items.map((item) => (
        <Tag key={item} className="!m-0">
          {item}
        </Tag>
      ))}
    </span>
  ) : (
    <Text type="secondary">无</Text>
  );
}

export function ElementLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <Button type="link" size="small" className="!h-auto !p-0" onClick={onClick}>
      {children}
    </Button>
  );
}

/** Name, technical name, description, synonyms and tags; shared by every editable resource. */
export function IdentityFields<T extends { name: string; technical_name: string; description: string; synonyms: string[] }>({
  value,
  onChange,
  tags,
}: {
  value: T;
  onChange: (patch: Partial<T>) => void;
  tags?: { value: string[]; onChange: (tags: string[]) => void };
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-x-4">
        <Form.Item label="名称" required>
          <Input aria-label="名称" value={value.name} onChange={(e) => onChange({ name: e.target.value } as Partial<T>)} />
        </Form.Item>
        <Form.Item label="技术名" required>
          <Input
            aria-label="技术名"
            className="font-mono"
            value={value.technical_name}
            onChange={(e) => onChange({ technical_name: e.target.value.trim() } as Partial<T>)}
          />
        </Form.Item>
      </div>
      <Form.Item label="描述">
        <Input.TextArea
          aria-label="描述"
          autoSize={{ minRows: 2, maxRows: 6 }}
          value={value.description}
          onChange={(e) => onChange({ description: e.target.value } as Partial<T>)}
        />
      </Form.Item>
      <div className={tags ? "grid grid-cols-2 gap-x-4" : ""}>
        <Form.Item label="同义词">
          <Select
            mode="tags"
            aria-label="同义词"
            open={false}
            placeholder="输入后回车"
            value={value.synonyms}
            onChange={(synonyms: string[]) => onChange({ synonyms } as Partial<T>)}
          />
        </Form.Item>
        {tags && (
          <Form.Item label="标签">
            <Select mode="tags" aria-label="标签" open={false} placeholder="输入后回车" value={tags.value} onChange={tags.onChange} />
          </Form.Item>
        )}
      </div>
    </>
  );
}


function ObjectBasicEditor(props: PanelProps<ObjectType>) {
  const { draft, type } = props;
  const update = (patch: Partial<ObjectType>) => changeType(props, patch);
  const changeParent = (value?: string) => {
    const nextParent = value ?? null;
    if (nextParent === type.extends) return;
    let next = upsert(draft, "object_types", { ...type, extends: nextParent, derived_by: [] });
    const ownMapping = mappingFor(next, type.id);
    if (ownMapping?.binding_mode === "shared_parent") {
      const hasMappedAncestor = lineage(next, type.id)
        .slice(1)
        .some((id) => Boolean(mappingFor(next, id)));
      if (!hasMappedAncestor) next = remove(next, "mappings", ownMapping.id);
    }
    props.change(next);
  };
  const titleChoices = effectiveProperties(draft, type.id).map((p) => ({ value: p.definition.id, label: p.definition.name }));
  return (
    <Form layout="vertical" component="div" className="max-w-[860px]">
      <IdentityFields value={type} onChange={update} tags={{ value: type.tags, onChange: (tags) => update({ tags }) }} />
      <div className="grid grid-cols-2 gap-x-4">
        <Form.Item label="父对象" extra="子对象继承父对象的属性、关系和规则。">
          <TreeSelect
            aria-label="父对象"
            allowClear
            showSearch
            treeNodeFilterProp="title"
            treeDefaultExpandAll
            placeholder="无（根对象）"
            value={type.extends ?? undefined}
            treeData={objectTree(draft, type.id)}
            onChange={changeParent}
          />
        </Form.Item>
        <Form.Item label="标题属性" extra="实例显示名称；不填时用标识。">
          <Select
            aria-label="标题属性"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="不指定"
            value={type.title_property_id ?? undefined}
            options={titleChoices}
            onChange={(value?: string) => update({ title_property_id: value ?? null })}
          />
        </Form.Item>
      </div>
      {type.extends && (
        <Form.Item label="成员条件">
          <DerivedConditionEditor
            key={`${type.id}:${type.extends}`}
            draft={draft}
            object={type}
            onChange={(derived_by) => update({ derived_by })}
          />
        </Form.Item>
      )}
    </Form>
  );
}

export function ObjectBasicPanel(props: PanelProps<ObjectType>) {
  const { draft, type, editing, open } = props;
  if (editing) return <ObjectBasicEditor {...props} />;
  const parent = byId(draft.object_types, type.extends);
  const kids = children(draft, type.id);
  const title = titleProperty(draft, type.id);
  const keys = identifier(draft, type.id);
  const record = objectMapping(draft, type);
  const items = [
    { key: "technical", label: "技术名", children: <code>{type.technical_name}</code> },
    {
      key: "parent",
      label: "父对象",
      children: parent ? (
        <ElementLink onClick={() => open({ kind: "object_type", id: parent.id })}>{parent.name}</ElementLink>
      ) : (
        <Text type="secondary">无（根对象）</Text>
      ),
    },
    ...(kids.length
      ? [
          {
            key: "children",
            label: "子对象",
            children: (
              <span className="flex flex-wrap gap-x-3">
                {kids.map((k) => (
                  <ElementLink key={k.id} onClick={() => open({ kind: "object_type", id: k.id })}>
                    {k.name}
                  </ElementLink>
                ))}
              </span>
            ),
          },
        ]
      : []),
    {
      key: "identifier",
      label: "标识",
      children: keys.length ? keys.map((p) => p.name).join(" + ") : <Text type="secondary">未设置</Text>,
    },
    { key: "title", label: "标题属性", children: title?.name ?? <Text type="secondary">未指定</Text> },
    {
      key: "binding",
      label: "实例来源",
      children: (
        <span className="flex flex-wrap items-center gap-2">
          {BINDING_MODES[record.mode]}
          {record.mode !== "virtual" && record.mode !== "unbound" && (
            <MappingStatusIcon state={record.state} label={record.label} />
          )}
          {record.main?.dataset && <Text type="secondary">主数据集：{record.main.dataset.name}</Text>}
        </span>
      ),
    },
    { key: "synonyms", label: "同义词", children: <TagsText items={type.synonyms} /> },
    { key: "tags", label: "标签", children: <TagsText items={type.tags} /> },
    ...(parent
      ? [{ key: "derived", label: "成员条件", span: "filled" as const, children: <DerivedSummary draft={draft} object={type} /> }]
      : []),
  ];
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
      <div className="flex min-w-0 flex-col gap-4">
        {type.description ? (
          <Paragraph className="!m-0 whitespace-pre-wrap">{type.description}</Paragraph>
        ) : (
          <Text type="secondary">暂无描述</Text>
        )}
        <Descriptions size="small" column={2} bordered items={items} />
        <EvidenceSection workspaceId={draft.workspace_id} evidence={type.evidence} />
      </div>
      <ObjectRelationGraph {...props} />
    </div>
  );
}

function LinkBasicEditor(props: PanelProps<LinkType>) {
  const { draft, type } = props;
  const update = (patch: Partial<LinkType>) => changeType(props, patch);
  const objects = draft.object_types.map((o) => ({ value: o.id, label: o.name || o.technical_name }));
  return (
    <Form layout="vertical" component="div" className="max-w-[860px]">
      <IdentityFields value={type} onChange={update} tags={{ value: type.tags, onChange: (tags) => update({ tags }) }} />
      <div className="grid grid-cols-3 gap-x-4">
        <Form.Item label="来源对象" required>
          <Select
            aria-label="来源对象"
            showSearch
            optionFilterProp="label"
            value={type.source_type_id || undefined}
            options={objects}
            onChange={(source_type_id: string) => update({ source_type_id, data_join: null })}
          />
        </Form.Item>
        <Form.Item label="目标对象" required>
          <Select
            aria-label="目标对象"
            showSearch
            optionFilterProp="label"
            value={type.target_type_id || undefined}
            options={objects}
            onChange={(target_type_id: string) => update({ target_type_id, data_join: null })}
          />
        </Form.Item>
        <Form.Item label="基数" required>
          <Select
            aria-label="基数"
            value={type.multiplicity}
            options={Object.entries(MULTIPLICITY).map(([value, label]) => ({ value, label }))}
            onChange={(multiplicity: LinkType["multiplicity"]) => update({ multiplicity })}
          />
        </Form.Item>
      </div>
      <Form.Item label="反向名称" extra="从目标对象看这条关系时的名称，可不填。">
        <Input
          aria-label="反向名称"
          value={type.inverse_name ?? ""}
          onChange={(e) => update({ inverse_name: e.target.value || null })}
        />
      </Form.Item>
    </Form>
  );
}

export function LinkBasicPanel(props: PanelProps<LinkType>) {
  const { draft, type, editing, open } = props;
  if (editing) return <LinkBasicEditor {...props} />;
  const source = byId(draft.object_types, type.source_type_id);
  const target = byId(draft.object_types, type.target_type_id);
  const endpoint = (object: ObjectType | undefined) =>
    object ? <ElementLink onClick={() => open({ kind: "object_type", id: object.id })}>{object.name}</ElementLink> : "?";
  return (
    <div className="flex max-w-[960px] flex-col gap-4">
      {type.description ? (
        <Paragraph className="!m-0 whitespace-pre-wrap">{type.description}</Paragraph>
      ) : (
        <Text type="secondary">暂无描述</Text>
      )}
      <Descriptions
        size="small"
        column={2}
        bordered
        items={[
          { key: "technical", label: "技术名", children: <code>{type.technical_name}</code> },
          { key: "multiplicity", label: "基数", children: MULTIPLICITY[type.multiplicity] },
          {
            key: "ends",
            label: "两端",
            span: 2,
            children: (
              <span className="inline-flex items-center gap-2">
                {endpoint(source)} → {endpoint(target)}
              </span>
            ),
          },
          { key: "inverse", label: "反向名称", children: type.inverse_name ?? <Text type="secondary">无</Text> },
          { key: "join", label: "数据绑定", children: joinSummary(draft, type.data_join) },
          { key: "synonyms", label: "同义词", children: <TagsText items={type.synonyms} /> },
          { key: "tags", label: "标签", children: <TagsText items={type.tags} /> },
        ]}
      />
      <EvidenceSection workspaceId={draft.workspace_id} evidence={type.evidence} />
    </div>
  );
}

// --- rules ---------------------------------------------------------------------

const RULE_KINDS: Record<Rule["rule_kind"], string> = { constraint: "约束", derivation: "派生说明" };

function ruleOwnerName(draft: Draft, rule: Rule) {
  if (rule.owner_kind === "object_type") return byId(draft.object_types, rule.owner_id)?.name ?? "?";
  if (rule.owner_kind === "link_type") return byId(draft.link_types, rule.owner_id)?.name ?? "?";
  const property = byId(draft.properties, rule.owner_id);
  return property ? `属性 ${property.name}` : "?";
}

/** Owners a new rule may attach to from this inspector (never inherited ones). */
function ruleOwners(draft: Draft, type: ObjectType | LinkType) {
  if (!("derived_by" in type)) return [{ value: `link_type:${type.id}`, label: type.name || "本关系" }];
  return [
    { value: `object_type:${type.id}`, label: type.name || "本对象" },
    ...draft.properties
      .filter((p) => p.owner_type_id === type.id)
      .map((p) => ({ value: `property:${p.id}`, label: `属性 ${p.name || p.technical_name}` })),
  ];
}

function isLocalRule(draft: Draft, type: ObjectType | LinkType, rule: Rule) {
  if (rule.owner_id === type.id) return true;
  return rule.owner_kind === "property" && byId(draft.properties, rule.owner_id)?.owner_type_id === type.id;
}

export function RulesPanel(props: PanelProps) {
  const { draft, type, editing, change } = props;
  const rules = rulesFor(draft, type);
  const setRule = (rule: Rule) => change({ ...draft, rules: draft.rules.map((r) => (r.id === rule.id ? rule : r)) });
  const owners = ruleOwners(draft, type);
  const addRule = () => {
    const [kind, id] = owners[0].value.split(":");
    change({
      ...draft,
      rules: [
        ...draft.rules,
        {
          id: newId(),
          name: "",
          technical_name: "",
          description: "",
          evidence: [],
          owner_kind: kind as Rule["owner_kind"],
          owner_id: id,
          rule_kind: "constraint",
          expression: "",
        },
      ],
    });
  };
  if (!editing)
    return rules.length ? (
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={rules}
        columns={[
          {
            title: "规则",
            key: "name",
            render: (_, r) => (
              <div className="flex flex-col">
                <span data-element-id={r.id}>{r.name}</span>
                <code className="text-xs text-muted">{r.technical_name}</code>
              </div>
            ),
          },
          { title: "类型", key: "kind", width: 96, render: (_, r) => <Tag className="!m-0">{RULE_KINDS[r.rule_kind]}</Tag> },
          {
            title: "所属",
            key: "owner",
            width: 160,
            render: (_, r) => (
              <span className="flex flex-col">
                {ruleOwnerName(draft, r)}
                {!isLocalRule(draft, type, r) && <Text type="secondary" className="text-xs">继承</Text>}
              </span>
            ),
          },
          {
            title: "表达式",
            key: "expression",
            render: (_, r) => (
              <div className="flex flex-col gap-1">
                <code className="whitespace-pre-wrap break-all">{r.expression}</code>
                {r.description && <Text type="secondary" className="text-xs">{r.description}</Text>}
              </div>
            ),
          },
        ]}
      />
    ) : (
      <Empty description="没有规则" />
    );
  return (
    <div className="flex max-w-[960px] flex-col gap-3">
      {rules.map((rule) => {
        const local = isLocalRule(draft, type, rule);
        return (
          <div key={rule.id} data-element-id={rule.id} className="rounded-md border border-rule p-3">
            {local ? (
              <Form layout="vertical" component="div">
                <div className="grid grid-cols-[1fr_1fr_140px_200px_32px] gap-x-3">
                  <Form.Item label="名称" required className="!mb-2">
                    <Input aria-label="规则名称" value={rule.name} onChange={(e) => setRule({ ...rule, name: e.target.value })} />
                  </Form.Item>
                  <Form.Item label="技术名" required className="!mb-2">
                    <Input
                      aria-label="规则技术名"
                      className="font-mono"
                      value={rule.technical_name}
                      onChange={(e) => setRule({ ...rule, technical_name: e.target.value.trim() })}
                    />
                  </Form.Item>
                  <Form.Item label="类型" className="!mb-2">
                    <Select
                      aria-label="规则类型"
                      value={rule.rule_kind}
                      options={Object.entries(RULE_KINDS).map(([value, label]) => ({ value, label }))}
                      onChange={(rule_kind: Rule["rule_kind"]) => setRule({ ...rule, rule_kind })}
                    />
                  </Form.Item>
                  <Form.Item label="所属" className="!mb-2">
                    <Select
                      aria-label="规则所属"
                      value={`${rule.owner_kind}:${rule.owner_id}`}
                      options={owners}
                      onChange={(value: string) => {
                        const [owner_kind, owner_id] = value.split(":");
                        setRule({ ...rule, owner_kind: owner_kind as Rule["owner_kind"], owner_id });
                      }}
                    />
                  </Form.Item>
                  <Button
                    type="text"
                    className="mt-7"
                    aria-label={`删除规则 ${rule.name}`}
                    icon={<Trash2 size={15} />}
                    onClick={() => change({ ...draft, rules: draft.rules.filter((r) => r.id !== rule.id) })}
                  />
                </div>
                <Form.Item label="表达式" required className="!mb-2">
                  <Input.TextArea
                    aria-label="规则表达式"
                    className="font-mono"
                    autoSize={{ minRows: 1, maxRows: 6 }}
                    value={rule.expression}
                    onChange={(e) => setRule({ ...rule, expression: e.target.value })}
                  />
                </Form.Item>
                <Form.Item label="说明" className="!mb-0">
                  <Input aria-label="规则说明" value={rule.description} onChange={(e) => setRule({ ...rule, description: e.target.value })} />
                </Form.Item>
              </Form>
            ) : (
              <div className="flex flex-col gap-1">
                <span>
                  {rule.name} <Text type="secondary">· 继承自{ruleOwnerName(draft, rule)}，在所属对象上修改</Text>
                </span>
                <code className="whitespace-pre-wrap break-all">{rule.expression}</code>
              </div>
            )}
          </div>
        );
      })}
      <Button type="dashed" icon={<Plus size={15} />} className="self-start" onClick={addRule}>
        添加规则
      </Button>
    </div>
  );
}
