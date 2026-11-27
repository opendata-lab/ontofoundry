import { Button, Descriptions, Empty, Input, Table, Tag, Typography } from "antd";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { Action, ActionEffect, ActionParameter, Draft, ObjectType } from "../../api/types";
import { ACTION_EFFECT_KINDS } from "../../lib/actionFormat";
import { VALUE_KINDS, byId, effectiveActions, type Inherited } from "../../lib/coreModel";
import type { ElementRequest } from "../../lib/elementInspector";
import { ContentBlock, DetailWorkbench, PanelToolbar, SectionTitle } from "../layout";
import { ElementLink, EvidenceSection, TagsText, ValueTypeSourceLink } from "./ElementPanels";

const { Text } = Typography;

/** Restrained status marker making clear actions are declarative definitions only. */
export function ActionDefinitionTag() {
  return <Tag className="m-0">仅定义</Tag>;
}

function ActionParametersTable({ draft, parameters }: { draft: Draft; parameters: ActionParameter[] }) {
  if (!parameters.length) return <Text type="secondary">无参数</Text>;
  return (
    <Table<ActionParameter>
      size="small"
      rowKey="name"
      pagination={false}
      dataSource={parameters}
      columns={[
        {
          title: "参数",
          key: "name",
          render: (_, p) => (
            <span className="flex flex-wrap items-baseline gap-1.5">
              <span className="font-medium">{p.display_name || p.name}</span>
              {p.display_name && <code className="text-xs text-muted">{p.name}</code>}
            </span>
          ),
        },
        {
          title: "类型",
          key: "type",
          render: (_, p) => {
            const vt = p.value_type_id ? byId(draft.value_types ?? [], p.value_type_id) : undefined;
            return (
              <span className="inline-flex flex-wrap items-center gap-1.5 whitespace-nowrap">
                <span>{VALUE_KINDS[p.value_kind]}</span>
                {vt && (
                  <span className="text-xs text-muted">
                    （<ValueTypeSourceLink workspaceId={draft.workspace_id} name={vt.display_name || vt.name} />）
                  </span>
                )}
              </span>
            );
          },
        },
        {
          title: "必填",
          key: "required",
          width: 64,
          render: (_, p) => (p.required ? "必填" : <Text type="secondary">可选</Text>),
        },
        {
          title: "说明",
          key: "description",
          render: (_, p) => (p.description ? <span className="whitespace-pre-wrap">{p.description}</span> : <Text type="secondary">—</Text>),
        },
      ]}
    />
  );
}

function effectTarget(draft: Draft, effect: ActionEffect, open: (request: ElementRequest) => void) {
  if (effect.kind === "set_property") {
    const prop = byId(draft.properties, effect.property_id);
    if (!prop) return <code>{effect.property_id}</code>;
    const owner = byId(draft.object_types, prop.owner_type_id);
    const label = owner ? `${owner.display_name || owner.name}.${prop.display_name || prop.name}` : prop.display_name || prop.name;
    return <ElementLink onClick={() => open({ kind: "property", id: prop.id })}>{label}</ElementLink>;
  }
  if (effect.kind === "add_link" || effect.kind === "remove_link") {
    const link = byId(draft.link_types, effect.link_type_id);
    if (!link) return <code>{effect.link_type_id}</code>;
    return <ElementLink onClick={() => open({ kind: "link_type", id: link.id })}>{link.display_name || link.name}</ElementLink>;
  }
  const obj = byId(draft.object_types, effect.object_type_id);
  if (!obj) return <code>{effect.object_type_id}</code>;
  return <ElementLink onClick={() => open({ kind: "object_type", id: obj.id })}>{obj.display_name || obj.name}</ElementLink>;
}

function effectKey(effect: ActionEffect) {
  if (effect.kind === "set_property") return `${effect.kind}:${effect.property_id}`;
  if (effect.kind === "add_link" || effect.kind === "remove_link") return `${effect.kind}:${effect.link_type_id}`;
  return `${effect.kind}:${effect.object_type_id}`;
}

function ActionEffectsTable({
  draft,
  effects,
  open,
}: {
  draft: Draft;
  effects: ActionEffect[];
  open: (request: ElementRequest) => void;
}) {
  if (!effects.length) return <Text type="secondary">未声明效果</Text>;
  return (
    <Table<ActionEffect>
      size="small"
      rowKey={effectKey}
      pagination={false}
      dataSource={effects}
      columns={[
        {
          title: "效果类型",
          key: "kind",
          width: 100,
          render: (_, e) => <Tag className="m-0">{ACTION_EFFECT_KINDS[e.kind]}</Tag>,
        },
        {
          title: "目标元素",
          key: "target",
          render: (_, e) => effectTarget(draft, e, open),
        },
        {
          title: "说明",
          key: "description",
          render: (_, e) => (e.description ? <span className="whitespace-pre-wrap">{e.description}</span> : <Text type="secondary">—</Text>),
        },
      ]}
    />
  );
}

/** Standalone read-only inspector body for one action definition (bound or global). */
export function ActionReadOnlyPanel({
  draft,
  action,
  open,
}: {
  draft: Draft;
  action: Action;
  open: (request: ElementRequest) => void;
}) {
  const target = action.target_type_id ? byId(draft.object_types, action.target_type_id) : undefined;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ContentBlock>
        <SectionTitle title="基本信息" />
        <Descriptions
          size="small"
          column={1}
          items={[
            {
              key: "name",
              label: "名称",
              children: action.display_name || <Text type="secondary">未填写</Text>,
            },
            {
              key: "technical",
              label: "英文标识",
              children: <code>{action.name}</code>,
            },
            {
              key: "target",
              label: "作用对象",
              children: target ? (
                <ElementLink onClick={() => open({ kind: "object_type", id: target.id })}>
                  {target.display_name || target.name}
                </ElementLink>
              ) : action.target_type_id ? (
                <code>{action.target_type_id}</code>
              ) : (
                <Tag className="m-0">全局动作</Tag>
              ),
            },
            {
              key: "description",
              label: "说明与前提",
              children: action.description ? (
                <span className="whitespace-pre-wrap">{action.description}</span>
              ) : (
                <Text type="secondary">暂无说明</Text>
              ),
            },
            {
              key: "synonyms",
              label: "同义词",
              children: <TagsText items={action.synonyms} />,
            },
            {
              key: "tags",
              label: "标签",
              children: <TagsText items={action.tags} />,
            },
          ]}
        />
        <Text type="secondary" className="text-xs">
          动作仅记录业务行为契约与影响，不包含可执行代码，平台不直接执行；如需调整请在建模对话中提出。
        </Text>
      </ContentBlock>
      <ContentBlock>
        <SectionTitle title="参数" note={`${action.parameters.length} 个`} />
        <ActionParametersTable draft={draft} parameters={action.parameters} />
      </ContentBlock>
      <ContentBlock>
        <SectionTitle title="声明效果" note={`${action.effects.length} 项`} />
        <ActionEffectsTable draft={draft} effects={action.effects} open={open} />
      </ContentBlock>
      <EvidenceSection workspaceId={draft.workspace_id} evidence={action.evidence} />
    </div>
  );
}

/** Read-only Actions tab inside an ObjectType inspector, including inherited actions. */
export function ObjectActionsPanel({
  draft,
  type,
  open,
}: {
  draft: Draft;
  type: ObjectType;
  open: (request: ElementRequest) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const all = effectiveActions(draft, type.id);
  const normalized = query.trim().toLowerCase();
  const rows = all.filter(({ definition: a }) =>
    !normalized ||
    [a.display_name ?? "", a.name, a.description, ...a.synonyms, ...a.tags]
      .join(" ")
      .toLowerCase()
      .includes(normalized),
  );
  const selected = rows.find((r) => r.definition.id === selectedId) ?? rows[0];
  const parentName = (id: string | null) => {
    if (!id) return null;
    const parent = byId(draft.object_types, id);
    return parent ? parent.display_name || parent.name : id;
  };
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <PanelToolbar inset={false} className="inspector-toolbar">
        <div className="inspector-toolbar-controls">
          <Input.Search
            className="inspector-search w-inspector-search"
            size="small"
            aria-label="搜索动作"
            placeholder="搜索动作名称、标识或说明"
            allowClear
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </PanelToolbar>
      <DetailWorkbench
        detailLabel="选中动作详情"
        primary={
          <>
            <SectionTitle title="动作" note={normalized ? `${rows.length} / ${all.length} 个` : `${all.length} 个`} />
            <Table<Inherited<Action>>
              size="small"
              rowKey={(r) => r.definition.id}
              pagination={false}
              dataSource={rows}
              onRow={(r) => ({
                onClick: () => setSelectedId(r.definition.id),
                className: r.definition.id === selected?.definition.id ? "inspector-selection-row cursor-pointer" : "cursor-pointer",
              })}
              locale={{
                emptyText: (
                  <Empty description={normalized ? "没有匹配的动作" : "尚未定义适用动作，可在建模对话中提出"} />
                ),
              }}
              columns={[
                {
                  title: "动作",
                  key: "name",
                  render: (_, r) => {
                    const inherited = parentName(r.inheritedFrom);
                    return (
                      <div className="flex min-w-0 flex-col gap-0.5" data-element-id={r.definition.id}>
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className={r.inheritedFrom ? "font-medium text-muted" : "font-medium"}>
                            {r.definition.display_name || r.definition.name}
                          </span>
                          <ActionDefinitionTag />
                        </span>
                        {inherited && (
                          <Text type="secondary" className="text-xs">
                            继承自 {inherited}
                          </Text>
                        )}
                      </div>
                    );
                  },
                },
                {
                  title: "参数 / 效果",
                  key: "counts",
                  width: 96,
                  render: (_, r) => (
                    <Text type="secondary" className="whitespace-nowrap text-xs">
                      {r.definition.parameters.length} / {r.definition.effects.length}
                    </Text>
                  ),
                },
                {
                  title: "操作",
                  key: "detail",
                  width: 72,
                  render: (_, r) => (
                    <Button
                      type="link"
                      size="small"
                      icon={<ChevronRight size={14} />}
                      iconPosition="end"
                      aria-label={`查看动作${r.definition.display_name || r.definition.name}详情`}
                      aria-pressed={r.definition.id === selected?.definition.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedId(r.definition.id);
                      }}
                    >
                      详情
                    </Button>
                  ),
                },
              ]}
            />
          </>
        }
        detail={
          selected ? (
            <>
              <ContentBlock>
                <SectionTitle title={selected.definition.display_name || selected.definition.name} note={selected.definition.name}>
                  <ActionDefinitionTag />
                  <Button
                    size="small"
                    type="link"
                    className="h-auto p-0"
                    onClick={() => open({ kind: "action", id: selected.definition.id })}
                  >
                    打开动作详情
                  </Button>
                </SectionTitle>
                {selected.inheritedFrom && (
                  <Text type="secondary" className="text-xs">
                    继承自{" "}
                    <ElementLink onClick={() => open({ kind: "object_type", id: selected.inheritedFrom! })}>
                      {parentName(selected.inheritedFrom)}
                    </ElementLink>
                    。
                  </Text>
                )}
                {selected.definition.description ? (
                  <p className="m-0 whitespace-pre-wrap text-sm">{selected.definition.description}</p>
                ) : (
                  <Text type="secondary">暂无说明</Text>
                )}
                {(selected.definition.synonyms.length > 0 || selected.definition.tags.length > 0) && (
                  <Descriptions
                    size="small"
                    column={1}
                    items={[
                      ...(selected.definition.synonyms.length
                        ? [{ key: "synonyms", label: "同义词", children: <TagsText items={selected.definition.synonyms} /> }]
                        : []),
                      ...(selected.definition.tags.length
                        ? [{ key: "tags", label: "标签", children: <TagsText items={selected.definition.tags} /> }]
                        : []),
                    ]}
                  />
                )}
              </ContentBlock>
              <ContentBlock>
                <SectionTitle title="参数" note={`${selected.definition.parameters.length} 个`} />
                <ActionParametersTable draft={draft} parameters={selected.definition.parameters} />
              </ContentBlock>
              <ContentBlock>
                <SectionTitle title="声明效果" note={`${selected.definition.effects.length} 项`} />
                <ActionEffectsTable draft={draft} effects={selected.definition.effects} open={open} />
              </ContentBlock>
              <EvidenceSection workspaceId={draft.workspace_id} evidence={selected.definition.evidence} />
            </>
          ) : (
            <ContentBlock>
              <Empty description="选择动作查看完整定义" />
            </ContentBlock>
          )
        }
      />
    </div>
  );
}
