import { Button, Descriptions, Empty, Form, Input, Select, Table, Tag, TreeSelect, Typography } from "antd";
import { ContentBlock, DetailWorkbench, PanelToolbar, SectionTitle } from "../layout";
import { ChevronRight, FileText, Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { Draft, Evidence, LinkType, ObjectType, Rule } from "../../api/types";
import {
  byId,
  children,
  effectiveProperties,
  lineage,
  mappingFor,
  remove,
  titleProperty,
  upsert,
} from "../../lib/coreModel";
import { changeType, objectTree, rulesFor, type PanelProps } from "../../lib/elementModel";
import { newId } from "../../lib/id";
import { DerivedConditionEditor, DerivedSummary } from "./DerivedConditionEditor";
import { ObjectRelationGraph } from "./ObjectRelationGraph";

const { Text } = Typography;

export function EvidenceSection({ workspaceId, evidence }: { workspaceId: string; evidence: Evidence[] }) {
  if (!evidence.length) return null;
  return (
    <ContentBlock>
      <SectionTitle title="来源证据" />
      {evidence.map((ev) => (
        <div key={ev.id} className="flex flex-col gap-1 border-l border-rule pl-3 text-sm">
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
    </ContentBlock>
  );
}

export function TagsText({ items }: { items: string[] }) {
  return items.length ? (
    <span className="flex flex-wrap gap-1">
      {items.map((item) => (
        <Tag key={item} className="m-0">
          {item}
        </Tag>
      ))}
    </span>
  ) : (
    <Text type="secondary">无</Text>
  );
}

/** Jumps to the catalog's value type tab, keeping the current modeling session. */
export function ValueTypeSourceLink({ workspaceId, name }: { workspaceId: string; name: string }) {
  const [params] = useSearchParams();
  const next = new URLSearchParams({ catalogTab: "values" });
  const session = params.get("session");
  if (session) next.set("session", session);
  return <Link to={`/workspaces/${workspaceId}/objects?${next}`}>值类型 {name}</Link>;
}

export function ElementLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <Button type="link" size="small" className="h-auto p-0" onClick={onClick}>
      {children}
    </Button>
  );
}

/** View and edit share their field positions and keep the neighbouring graph in place. */
export function ObjectBasicPanel(props: PanelProps<ObjectType>) {
  const { draft, type, editing, open } = props;
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
  const titleChoices = effectiveProperties(draft, type.id).map((p) => ({ value: p.definition.id, label: (p.definition.display_name || p.definition.name) }));
  const parent = byId(draft.object_types, type.extends);
  const kids = children(draft, type.id);
  const title = titleProperty(draft, type.id);
  const items = [
    { key: "name", label: "名称", children: editing ? <Input aria-label="名称" value={type.display_name ?? ""} onChange={(event) => update({ display_name: event.target.value })} /> : type.display_name || <span className="text-muted">未填写</span> },
    { key: "technical", label: "英文标识", children: editing ? <Input aria-label="英文标识" className="font-mono" value={type.name} onChange={(event) => update({ name: event.target.value.trim() })} /> : <code>{type.name}</code> },
    { key: "description", label: "描述", children: editing ? <Input.TextArea aria-label="描述" autoSize={{ minRows: 1, maxRows: 6 }} value={type.description} onChange={(event) => update({ description: event.target.value })} /> : type.description ? <span className="whitespace-pre-wrap">{type.description}</span> : <Text type="secondary">暂无描述</Text> },
    { key: "parent", label: "父对象", children: editing ? <TreeSelect aria-label="父对象" className="w-full" allowClear showSearch treeNodeFilterProp="title" treeDefaultExpandAll placeholder="无（根对象）" value={type.extends ?? undefined} treeData={objectTree(draft, type.id)} onChange={changeParent} /> : parent ? <ElementLink onClick={() => open({ kind: "object_type", id: parent.id })}>{parent.display_name || parent.name}</ElementLink> : <Text type="secondary">无（根对象）</Text> },
    ...(parent ? [{ key: "derived", label: "成员条件", children: editing ? <DerivedConditionEditor key={`${type.id}:${type.extends}`} draft={draft} object={type} onChange={(derived_by) => update({ derived_by })} /> : <DerivedSummary draft={draft} object={type} /> }] : []),
    ...(kids.length ? [{ key: "children", label: "子对象", children: <span className="flex flex-wrap gap-x-3">{kids.map((child) => <ElementLink key={child.id} onClick={() => open({ kind: "object_type", id: child.id })}>{child.display_name || child.name}</ElementLink>)}</span> }] : []),
    { key: "title", label: "标题属性", children: editing ? <Select aria-label="标题属性" className="w-full" allowClear showSearch optionFilterProp="label" placeholder="不指定" value={type.title_property_id ?? undefined} options={titleChoices} onChange={(value?: string) => update({ title_property_id: value ?? null })} /> : (title?.display_name || title?.name) ?? <Text type="secondary">未指定</Text> },
    { key: "synonyms", label: "同义词", children: editing ? <Select mode="tags" aria-label="同义词" className="w-full" open={false} placeholder="输入后回车" value={type.synonyms} onChange={(synonyms: string[]) => update({ synonyms })} /> : <TagsText items={type.synonyms} /> },
    { key: "tags", label: "标签", children: editing ? <Select mode="tags" aria-label="标签" className="w-full" open={false} placeholder="输入后回车" value={type.tags} onChange={(tags: string[]) => update({ tags })} /> : <TagsText items={type.tags} /> },
  ];
  return (
    <div className="object-overview">
      <div className="object-overview-columns">
        <div className="object-overview-info flex min-w-0 flex-col gap-4">
          <ContentBlock className="flex-1">
            <SectionTitle title="基本信息" className="min-h-7" />
            <Form component="div" size="small"><Descriptions size="small" column={1} items={items} /></Form>
          </ContentBlock>
          <EvidenceSection workspaceId={draft.workspace_id} evidence={type.evidence} />
        </div>
        <ContentBlock><ObjectRelationGraph {...props} /></ContentBlock>
      </div>
    </div>
  );
}

// --- rules ---------------------------------------------------------------------

const RULE_KINDS: Record<Rule["rule_kind"], string> = { constraint: "约束", derivation: "派生说明" };

function ruleOwnerName(draft: Draft, rule: Rule) {
  if (rule.owner_kind === "object_type") return (byId(draft.object_types, rule.owner_id)?.display_name || byId(draft.object_types, rule.owner_id)?.name) ?? "?";
  if (rule.owner_kind === "link_type") return (byId(draft.link_types, rule.owner_id)?.display_name || byId(draft.link_types, rule.owner_id)?.name) ?? "?";
  if (rule.owner_kind === "value_type") {
    const shared = byId(draft.value_types ?? [], rule.owner_id);
    return shared ? `值类型 ${shared.display_name || shared.name}` : "?";
  }
  const property = byId(draft.properties, rule.owner_id);
  return property ? `属性 ${(property.display_name || property.name)}` : "?";
}

function valueTypeName(draft: Draft, rule: Rule) {
  const shared = byId(draft.value_types ?? [], rule.owner_id);
  return shared ? shared.display_name || shared.name : "?";
}

/** Owners a new rule may attach to from this inspector (never inherited ones). */
function ruleOwners(draft: Draft, type: ObjectType | LinkType) {
  if (!("derived_by" in type)) return [{ value: `link_type:${type.id}`, label: (type.display_name || type.name) || "本关系" }];
  return [
    { value: `object_type:${type.id}`, label: (type.display_name || type.name) || "本对象" },
    ...draft.properties
      .filter((p) => p.owner_type_id === type.id)
      .map((p) => ({ value: `property:${p.id}`, label: `属性 ${(p.display_name || p.name) || p.name}` })),
  ];
}

function isLocalRule(draft: Draft, type: ObjectType | LinkType, rule: Rule) {
  if (rule.owner_id === type.id) return true;
  return rule.owner_kind === "property" && byId(draft.properties, rule.owner_id)?.owner_type_id === type.id;
}

export function RulesPanel(props: PanelProps & { initialRuleId?: string }) {
  const { draft, type, editing, canEdit, change, initialRuleId } = props;
  const [selectedId, setSelectedId] = useState<string | null>(initialRuleId ?? null);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<"all" | Rule["rule_kind"]>("all");
  const rules = rulesFor(draft, type);
  const rows = rules.filter((r) => (kind === "all" || r.rule_kind === kind) &&
    `${(r.display_name || r.name)} ${r.name} ${r.expression} ${r.description}`.toLowerCase().includes(query.trim().toLowerCase()));
  const rule = rows.find((r) => r.id === selectedId) ?? rows[0];
  const editable = rule && editing && isLocalRule(draft, type, rule);
  const setRule = (value: Rule) => change({ ...draft, rules: draft.rules.map((r) => r.id === value.id ? value : r) });
  const owners = ruleOwners(draft, type);
  const addRule = () => {
    const [ownerKind, ownerId] = owners[0].value.split(":");
    const id = newId();
    setQuery("");
    setKind("all");
    setSelectedId(id);
    change({ ...draft, rules: [...draft.rules, {
      id, display_name: "", name: "", description: "", evidence: [],
      owner_kind: ownerKind as Rule["owner_kind"], owner_id: ownerId, rule_kind: "constraint", expression: "",
    }] });
  };
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <PanelToolbar inset={false} className="inspector-toolbar" extra={editing ? <Button size="small" icon={<Plus size={14} />} onClick={addRule}>添加规则</Button> : undefined}>
        <div className="inspector-toolbar-controls">
          <Input.Search className="inspector-search w-inspector-search" size="small" aria-label="搜索规则" placeholder="搜索规则名称或内容" allowClear value={query} onChange={(e) => setQuery(e.target.value)} />
          <Select className="inspector-filter min-w-inspector-filter" size="small" aria-label="筛选规则类型" value={kind} onChange={setKind} options={[{ value: "all", label: "全部类型" }, ...Object.entries(RULE_KINDS).map(([value, label]) => ({ value, label }))]} />
        </div>
      </PanelToolbar>
      <DetailWorkbench detailLabel="选中规则详情" primary={
        <>
          <SectionTitle title="规则" note={query || kind !== "all" ? `${rows.length} / ${rules.length} 条` : `${rules.length} 条`} />
          <Table<Rule>
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={rows}
            onRow={(r) => ({ onClick: () => setSelectedId(r.id), className: r.id === rule?.id ? "inspector-selection-row cursor-pointer" : "cursor-pointer" })}
            locale={{ emptyText: <Empty description={query || kind !== "all" ? "没有匹配的规则" : !editing && canEdit ? "尚未定义规则，可通过顶部编辑添加" : "尚未定义规则"} /> }}
            columns={[
              { title: "规则", key: "name", render: (_, r) => <div className="flex min-w-0 flex-col" data-element-id={r.id}><span className={isLocalRule(draft, type, r) ? "font-medium" : "font-medium text-muted"}>{(r.display_name || r.name) || "未命名规则"}</span>{!isLocalRule(draft, type, r) && <Text type="secondary" className="text-xs">{r.owner_kind === "value_type" ? <>继承自<ValueTypeSourceLink workspaceId={draft.workspace_id} name={valueTypeName(draft, r)} />，只读</> : "继承，只读"}</Text>}</div> },
              { title: "类型", key: "kind", render: (_, r) => RULE_KINDS[r.rule_kind] },
              { title: "所属", key: "owner", render: (_, r) => ruleOwnerName(draft, r) },
              { title: "操作", key: "detail", render: (_, r) => <Button type="link" size="small" icon={<ChevronRight size={14} />} iconPosition="end" aria-label={`查看规则${r.display_name || r.name || "未命名规则"}详情`} aria-pressed={r.id === rule?.id} onClick={(event) => { event.stopPropagation(); setSelectedId(r.id); }}>详情</Button> },
            ]}
          />
        </>
      } detail={rule ? (
        <>
          <ContentBlock>
            <SectionTitle title={(rule.display_name || rule.name) || "未命名规则"} note={rule.name}>
              {editable && <Button danger type="text" size="small" icon={<Trash2 size={14} />} aria-label={`删除规则 ${(rule.display_name || rule.name)}`} onClick={() => change({ ...draft, rules: draft.rules.filter((r) => r.id !== rule.id) })}>删除</Button>}
            </SectionTitle>
            {!isLocalRule(draft, type, rule) && <Text type="secondary">{rule.owner_kind === "value_type" ? <>继承自<ValueTypeSourceLink workspaceId={draft.workspace_id} name={valueTypeName(draft, rule)} />，在值类型中修改。</> : <>继承自{ruleOwnerName(draft, rule)}，在所属对象上修改。</>}</Text>}
            {editable ? (
              <Form layout="vertical" component="div" size="small">
                <Form.Item className="mb-3" label="名称"><Input aria-label="规则名称" value={rule.display_name ?? ""} onChange={(e) => setRule({ ...rule, display_name: e.target.value })} /></Form.Item>
                <Form.Item className="mb-3" label="英文标识" required><Input aria-label="规则英文标识" className="font-mono" value={rule.name} onChange={(e) => setRule({ ...rule, name: e.target.value.trim() })} /></Form.Item>
                <Form.Item className="mb-3" label="类型"><Select aria-label="规则类型" value={rule.rule_kind} options={Object.entries(RULE_KINDS).map(([value, label]) => ({ value, label }))} onChange={(rule_kind: Rule["rule_kind"]) => setRule({ ...rule, rule_kind })} /></Form.Item>
                <Form.Item className="mb-0" label="所属"><Select aria-label="规则所属" value={`${rule.owner_kind}:${rule.owner_id}`} options={owners} onChange={(value: string) => { const [owner_kind, owner_id] = value.split(":"); setRule({ ...rule, owner_kind: owner_kind as Rule["owner_kind"], owner_id }); }} /></Form.Item>
              </Form>
            ) : <Descriptions size="small" column={1} items={[
              { key: "technical", label: "英文标识", children: <code>{rule.name || "—"}</code> },
              { key: "kind", label: "类型", children: RULE_KINDS[rule.rule_kind] },
              { key: "owner", label: "所属", children: ruleOwnerName(draft, rule) },
            ]} />}
          </ContentBlock>
          <ContentBlock>
            <SectionTitle title="规则内容" />
            {editable ? <Form layout="vertical" component="div" size="small">
              <Form.Item className="mb-0" label="表达式" required><Input.TextArea aria-label="规则表达式" className="font-mono" autoSize={{ minRows: 4, maxRows: 12 }} value={rule.expression} onChange={(e) => setRule({ ...rule, expression: e.target.value })} /></Form.Item>
            </Form> : <code className="whitespace-pre-wrap break-words">{rule.expression || "尚未设置表达式"}</code>}
          </ContentBlock>
          <ContentBlock>
            <SectionTitle title="说明" />
            {editable ? <Form layout="vertical" component="div" size="small">
              <Form.Item label="说明" className="mb-0"><Input.TextArea aria-label="规则说明" autoSize={{ minRows: 2, maxRows: 6 }} value={rule.description} onChange={(e) => setRule({ ...rule, description: e.target.value })} /></Form.Item>
            </Form> : <Text type="secondary" className="whitespace-pre-wrap">{rule.description || "暂无说明"}</Text>}
          </ContentBlock>
          <EvidenceSection workspaceId={draft.workspace_id} evidence={rule.evidence} />
        </>
      ) : <ContentBlock><Empty description="选择规则查看完整内容" /></ContentBlock>} />
    </div>
  );
}
