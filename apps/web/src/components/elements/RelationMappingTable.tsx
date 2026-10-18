import { Button, Empty, Table, Tag, Typography } from "antd";
import { PanelToolbar, SectionTitle } from "../layout";
import { Plus } from "lucide-react";
import { useState } from "react";
import type { DataJoin, ObjectType } from "../../api/types";
import { MULTIPLICITY, bindingMode, byId, joinSummary } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { objectMapping, type MappedRelation } from "../../lib/objectMapping";
import { setInheritedLinkBinding } from "../../lib/objectMappingEditing";
import { relationEditReason } from "../../lib/relationEditing";
import { ElementLink } from "./ElementPanels";
import { InspectorDialog } from "./InspectorDialog";
import { joinProblem } from "../../lib/objectMappingEditing";
import { LinkJoinEditor } from "./LinkMappingPanel";
import { ReadonlyIcon } from "./MappingWidgets";

const { Text } = Typography;

/** Every effective relation of an object, both directions, with its data binding. */
export function RelationsPanel(props: PanelProps<ObjectType>) {
  const { draft, type, editing, canEdit, change, open } = props;
  const [binding, setBinding] = useState<{ relation: MappedRelation; join: DataJoin | null } | null>(null);
  const relations = objectMapping(draft, type).relations;
  const concrete = bindingMode(draft, type.id) === "independent";
  const other = (r: MappedRelation) =>
    byId(draft.object_types, r.direction === "forward" ? r.definition.target_type_id : r.definition.source_type_id);
  const endpoints = (r: MappedRelation) => {
    // The inherited end is played by this object when it binds the relation locally.
    const source = r.direction === "forward" ? type.id : r.definition.source_type_id;
    const target = r.direction === "forward" ? r.definition.target_type_id : type.id;
    return { source, target };
  };
  return (
    <div className="flex flex-col gap-3">
      <PanelToolbar className="px-0" extra={!editing && canEdit ? (
        <Button
          icon={<Plus size={15} />}
          className="self-start"
          onClick={() => open({ kind: "link_type", id: "new", owner: type.id, mode: "edit" })}
        >
          新建关系
        </Button>
      ) : undefined}>
        <SectionTitle title="关系" />
      </PanelToolbar>
      {relations.length ? (
        <Table
          size="small"
          rowKey={(r) => r.definition.id}
          pagination={false}
          dataSource={relations}
          columns={[
            {
              title: "关系",
              key: "name",
              render: (_, r) => (
                <div className="flex flex-col" data-element-id={r.definition.id}>
                  <ElementLink onClick={() => open({ kind: "link_type", id: r.definition.id })}>
                    {r.direction === "reverse" && r.definition.inverse_name ? r.definition.inverse_name : r.definition.name}
                  </ElementLink>
                  <code className="text-xs text-muted">{r.definition.technical_name}</code>
                </div>
              ),
            },
            {
              title: "对端对象",
              key: "other",
              render: (_, r) => {
                const object = other(r);
                return (
                  <span className="inline-flex items-center gap-1">
                    <Text type="secondary">{r.direction === "forward" ? "→" : "←"}</Text>
                    {object ? (
                      <ElementLink onClick={() => open({ kind: "object_type", id: object.id })}>{object.name}</ElementLink>
                    ) : (
                      "?"
                    )}
                  </span>
                );
              },
            },
            { title: "基数", key: "multiplicity", width: 88, render: (_, r) => MULTIPLICITY[r.definition.multiplicity] },
            {
              title: "定义",
              key: "owner",
              width: 140,
              render: (_, r) =>
                r.inheritedFrom ? (
                  <Text type="secondary">继承自{byId(draft.object_types, r.inheritedFrom)?.name ?? "?"}</Text>
                ) : (
                  "本对象"
                ),
            },
            {
              title: "数据绑定",
              key: "join",
              render: (_, r) => {
                const reason = relationEditReason(draft, type.id, r);
                const editable = editing && concrete && !reason;
                return (
                  <span className="flex flex-wrap items-center gap-2">
                    {joinSummary(draft, r.join)}
                    {r.local && <Tag className="m-0">本对象绑定</Tag>}
                    {editing && !editable && <ReadonlyIcon reason={reason ?? "先为本对象独立绑定数据集"} />}
                    {editable && (
                      <Button size="small" onClick={() => setBinding({ relation: r, join: r.local ? r.join : null })}>
                        绑定
                      </Button>
                    )}
                  </span>
                );
              },
            },
          ]}
        />
      ) : (
        <Empty description="没有关系" />
      )}
      {binding && (
        <InspectorDialog
          wide
          title={`绑定继承关系：${binding.relation.definition.name}`}
          subtitle="只在本对象上生效，不改动父对象的关系定义。"
          onClose={() => setBinding(null)}
          footer={
            <div className="flex justify-end gap-2">
              <Button onClick={() => setBinding(null)}>取消</Button>
              <Button
                type="primary"
                disabled={!!joinProblem(binding.join) || undefined}
                onClick={() => {
                  change(setInheritedLinkBinding(draft, type.id, binding.relation.definition.id, binding.join));
                  setBinding(null);
                }}
              >
                确定
              </Button>
            </div>
          }
        >
          <LinkJoinEditor
            draft={draft}
            {...{
              sourceTypeId: endpoints(binding.relation).source,
              targetTypeId: endpoints(binding.relation).target,
            }}
            value={binding.join}
            onChange={(join) => setBinding({ ...binding, join })}
          />
        </InspectorDialog>
      )}
    </div>
  );
}
