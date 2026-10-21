import { Button, Descriptions, Empty, Input, Table, Typography } from "antd";
import { ContentBlock, DetailWorkbench, PanelToolbar, SectionTitle } from "../layout";
import { ArrowRight, ChevronRight, Plus } from "lucide-react";
import { useState } from "react";
import type { ObjectType } from "../../api/types";
import { MULTIPLICITY, linkDisplayName, bindingMode, byId, joinSummary } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { objectMapping, type MappedRelation } from "../../lib/objectMapping";
import { setInheritedLinkBinding } from "../../lib/objectMappingEditing";
import { isForwardReading, renderLinkReading } from "../../lib/linkReadings";
import { relationEditReason } from "../../lib/relationEditing";
import { ElementLink, EvidenceSection } from "./ElementPanels";
import { LinkJoinEditor } from "./LinkMappingPanel";

const { Text } = Typography;
const relationKey = (relation: MappedRelation) => `${relation.definition.id}:${relation.direction}`;

/** Browse business connections before opening their complete definition and binding. */
export function RelationsPanel(props: PanelProps<ObjectType>) {
  const { draft, type, editing, canEdit, change, open } = props;
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const relations = objectMapping(draft, type).relations;
  const concrete = bindingMode(draft, type.id) === "independent";
  const other = (r: MappedRelation) =>
    byId(draft.object_types, r.direction === "forward" ? r.definition.target_type_id : r.definition.source_type_id);
  const displayName = (r: MappedRelation) => linkDisplayName(r.definition, r.direction === "forward");
  const rows = relations.filter((r) =>
    `${displayName(r)} ${(r.definition.display_name || r.definition.name)} ${(r.definition.display_name || r.definition.name)} ${(other(r)?.display_name || other(r)?.name) ?? ""}`
      .toLowerCase().includes(query.trim().toLowerCase()));
  const selected = rows.find((r) => relationKey(r) === selectedId) ?? rows[0];
  const reason = selected ? relationEditReason(draft, type.id, selected) : null;
  const editable = editing && concrete && selected && !reason;
  const endpoints = (r: MappedRelation) => ({
    // The inherited end is played by this object when it binds the relation locally.
    source: r.direction === "forward" ? type.id : r.definition.source_type_id,
    target: r.direction === "forward" ? r.definition.target_type_id : type.id,
  });
  const endpoint = (id: string) => {
    const object = byId(draft.object_types, id);
    return object ? <ElementLink onClick={() => open({ kind: "object_type", id })}>{(object.display_name || object.name)}</ElementLink> : <Text type="secondary">对象不存在</Text>;
  };
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <PanelToolbar inset={false} className="inspector-toolbar" extra={!editing && canEdit ? (
        <Button size="small" icon={<Plus size={14} />} onClick={() => open({ kind: "link_type", id: "new", owner: type.id, mode: "edit" })}>新建关系</Button>
      ) : undefined}>
        <Input.Search className="inspector-search w-inspector-search" size="small" aria-label="搜索关系" placeholder="搜索关系或对端对象" allowClear value={query} onChange={(e) => setQuery(e.target.value)} />
      </PanelToolbar>
      <DetailWorkbench detailLabel="选中关系详情" primary={
        <>
          <SectionTitle title="关系" note={query ? `${rows.length} / ${relations.length} 条` : `${relations.length} 条`} />
          <Table<MappedRelation>
            size="small"
            rowKey={relationKey}
            pagination={false}
            dataSource={rows}
            onRow={(r) => ({ onClick: () => setSelectedId(relationKey(r)), className: relationKey(r) === (selected && relationKey(selected)) ? "inspector-selection-row cursor-pointer" : "cursor-pointer" })}
            locale={{ emptyText: <Empty description={query ? "没有匹配的关系" : "尚未定义关系"} /> }}
            columns={[
              { title: "关系", key: "name", render: (_, r) => (
                <div className="flex min-w-0 flex-col" data-element-id={r.definition.id}>
                  <span className="font-medium">{displayName(r) || "未命名关系"}</span>
                  <Text type="secondary" className="text-xs">{r.inheritedFrom ? `继承自${(byId(draft.object_types, r.inheritedFrom)?.display_name || byId(draft.object_types, r.inheritedFrom)?.name) ?? "父对象"}` : "本对象定义"}</Text>
                </div>
              ) },
              { title: "对端对象", key: "other", render: (_, r) => <span>{r.direction === "forward" ? "→" : "←"} {(other(r)?.display_name || other(r)?.name) ?? "—"}</span> },
              { title: "基数", key: "multiplicity", render: (_, r) => MULTIPLICITY[r.definition.multiplicity] },
              { title: "操作", key: "detail", render: (_, r) => <Button type="link" size="small" icon={<ChevronRight size={14} />} iconPosition="end" aria-label={`查看关系${displayName(r) || "未命名关系"}详情`} aria-pressed={relationKey(r) === (selected && relationKey(selected))} onClick={(event) => { event.stopPropagation(); setSelectedId(relationKey(r)); }}>详情</Button> },
            ]}
          />
        </>
      } detail={selected ? (
        <>
          <ContentBlock>
            <SectionTitle title={<ElementLink onClick={() => open({ kind: "link_type", id: selected.definition.id })}>{(selected.definition.display_name || selected.definition.name) || "未命名关系"}</ElementLink>} note={selected.direction === "forward" ? undefined : "反向"} />
            <div className="flex flex-wrap items-center gap-2">
              {endpoint(endpoints(selected).source)}
              <ArrowRight size={14} className="shrink-0 text-muted" />
              {endpoint(endpoints(selected).target)}
            </div>
            {/* The meaning reads the link once; the identifier already heads this pane. */}
            {(() => {
              const reading = selected.definition.verbalizes.find(isForwardReading);
              return reading ? <Text type="secondary">{renderLinkReading(draft, selected.definition, reading)}</Text> : null;
            })()}
          </ContentBlock>
          <ContentBlock>
            <SectionTitle title="基本信息" />
            <Descriptions size="small" column={1} items={[
              { key: "source_role", label: "来源端角色名", children: selected.definition.source_role_name || "未设置" },
              { key: "target_role", label: "目标端角色名", children: selected.definition.target_role_name || "未设置" },

              { key: "multiplicity", label: "基数", children: MULTIPLICITY[selected.definition.multiplicity] },
              { key: "owner", label: "定义来源", children: selected.inheritedFrom ? (byId(draft.object_types, selected.inheritedFrom)?.display_name || byId(draft.object_types, selected.inheritedFrom)?.name) ?? "父对象" : "本对象" },
              { key: "description", label: "描述", children: <span className="whitespace-pre-wrap">{selected.definition.description || "暂无描述"}</span> },
            ]} />
          </ContentBlock>
          <ContentBlock>
            <SectionTitle title="数据绑定" note={selected.local ? "本对象绑定" : undefined} />
            {editable ? (
              <LinkJoinEditor
                draft={draft}
                sourceTypeId={endpoints(selected).source}
                targetTypeId={endpoints(selected).target}
                value={selected.local ? selected.join : null}
                onChange={(join) => change(setInheritedLinkBinding(draft, type.id, selected.definition.id, join))}
              />
            ) : (
              <>
                <Text className="whitespace-pre-wrap">{joinSummary(draft, selected.join)}</Text>
                {editing && <Text type="secondary" className="text-xs">{reason ?? "先为本对象独立绑定数据集"}</Text>}
              </>
            )}
          </ContentBlock>
          <EvidenceSection workspaceId={draft.workspace_id} evidence={selected.definition.evidence} />
        </>
      ) : <ContentBlock><Empty description="选择关系查看定义与数据绑定" /></ContentBlock>} />
    </div>
  );
}
