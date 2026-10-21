import { Button, Descriptions, Form, Input, Select, Typography } from "antd";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useRef } from "react";
import type { DataJoin, LinkType } from "../../api/types";
import { byId, effectiveProperties } from "../../lib/coreModel";
import { changeType, type PanelProps } from "../../lib/elementModel";
import { ContentBlock, FormRow, SectionTitle } from "../layout";
import { RelationshipConnection } from "./RelationshipConnection";
import { ElementInstances } from "./ElementInstances";
import { EvidenceSection, TagsText } from "./ElementPanels";

const { Text } = Typography;
type DirectJoin = Extract<DataJoin, { kind: "direct" }>;

/** Keeps the business connection and its concrete instances in one overview. */
export function LinkOverviewPanel(props: PanelProps<LinkType> & {
  showInstances: boolean;
  initialInstances: boolean;
  canBrowseDatabase: boolean;
}) {
  const { draft, type, editing, showInstances, initialInstances, canBrowseDatabase } = props;
  const instances = useRef<HTMLElement>(null);
  useEffect(() => {
    if (initialInstances) instances.current?.scrollIntoView({ block: "start" });
  }, [initialInstances]);
  const update = (patch: Partial<LinkType>) => changeType(props, patch);
  const direct: DirectJoin = type.data_join?.kind === "direct" ? type.data_join : {
    kind: "direct", source_property_ids: [""], target_property_ids: [""],
  };
  const propertyName = (id: string) => (byId(draft.properties, id)?.display_name || byId(draft.properties, id)?.name) || "未选择属性";
  const directProperty = (side: "source" | "target", index: number) => {
    const ids = side === "source" ? direct.source_property_ids : direct.target_property_ids;
    const objectId = side === "source" ? type.source_type_id : type.target_type_id;
    return <Select
      className="min-w-0 flex-1"
      aria-label={`第 ${index + 1} 组${side === "source" ? "来源" : "目标"}属性`}
      showSearch optionFilterProp="label" placeholder="选择属性"
      value={ids[index] || undefined}
      options={effectiveProperties(draft, objectId).map(({ definition }) => ({ value: definition.id, label: (definition.display_name || definition.name) || definition.name }))}
      onChange={(value: string) => {
        const next = [...ids];
        next[index] = value;
        update({ data_join: side === "source"
          ? { ...direct, source_property_ids: next as [string, ...string[]] }
          : { ...direct, target_property_ids: next as [string, ...string[]] } });
      }}
    />;
  };
  return <div className="flex min-w-0 flex-col gap-4">
    <ContentBlock>
      <SectionTitle title="基本信息" />
      {editing ? <Form layout="vertical" component="div" size="small" className="fabric-relationship-form flex min-w-0 flex-col gap-3">
        <FormRow>
          <Form.Item className="mb-0" label="名称（中文）"><Input aria-label="关系名称（中文）" value={type.display_name ?? ""} onChange={(e) => update({ display_name: e.target.value })} /></Form.Item>
          <Form.Item className="mb-0" label="英文标识" required><Input aria-label="英文标识" value={type.name} onChange={(e) => update({ name: e.target.value.trim() })} /></Form.Item>
        </FormRow>
        <Form.Item className="mb-0" label="描述"><Input.TextArea aria-label="关系描述" autoSize={{ minRows: 2, maxRows: 6 }} value={type.description} onChange={(e) => update({ description: e.target.value })} /></Form.Item>
        <FormRow>
          <Form.Item className="mb-0" label="同义词"><Select mode="tags" className="w-full" aria-label="关系同义词" value={type.synonyms} onChange={(synonyms: string[]) => update({ synonyms })} /></Form.Item>
          <Form.Item className="mb-0" label="标签"><Select mode="tags" className="w-full" aria-label="关系标签" value={type.tags} onChange={(tags: string[]) => update({ tags })} /></Form.Item>
        </FormRow>
      </Form> : <Descriptions size="small" column={2} items={[
        { key: "name", label: "名称", children: type.display_name || <span className="text-muted">未填写</span> },
        { key: "identifier", label: "英文标识", children: <code>{type.name}</code> },
        ...(type.description ? [{ key: "description", label: "描述", span: 2, children: type.description }] : []),
        ...(type.synonyms.length ? [{ key: "synonyms", label: "同义词", children: <TagsText items={type.synonyms} /> }] : []),
        ...(type.tags.length ? [{ key: "tags", label: "标签", children: <TagsText items={type.tags} /> }] : []),
      ]} />}
    </ContentBlock>
    <ContentBlock><RelationshipConnection key={`${type.id}:${editing ? "edit" : "read"}`} {...props} /></ContentBlock>
    {(type.data_join?.kind === "direct" || (editing && !type.data_join)) && <ContentBlock>
      <SectionTitle title="关联属性" note="两端属性按顺序对应" />
      {direct.source_property_ids.map((id, index) => <FormRow key={index}>
        {editing ? directProperty("source", index) : <Text>{propertyName(id)}</Text>}
        {editing ? <div className="flex min-w-0 items-center gap-2">
          {directProperty("target", index)}
          {direct.source_property_ids.length > 1 && <Button type="text" size="small" icon={<Trash2 size={14} />} aria-label={`删除第 ${index + 1} 组对应`} onClick={() => update({ data_join: {
            ...direct,
            source_property_ids: direct.source_property_ids.filter((_, i) => i !== index) as [string, ...string[]],
            target_property_ids: direct.target_property_ids.filter((_, i) => i !== index) as [string, ...string[]],
          } })} />}
        </div> : <Text>{propertyName(direct.target_property_ids[index])}</Text>}
      </FormRow>)}
      {editing && <div className="flex flex-wrap items-center gap-2">
        <Button type="text" size="small" icon={<Plus size={14} />} onClick={() => update({ data_join: { ...direct, source_property_ids: [...direct.source_property_ids, ""], target_property_ids: [...direct.target_property_ids, ""] } })}>添加一组对应</Button>
        {type.data_join && <Button danger type="text" size="small" onClick={() => update({ data_join: null })}>解除数据绑定</Button>}
      </div>}
    </ContentBlock>}
    {showInstances && <ContentBlock ref={instances} aria-label="关系实例">
      <SectionTitle title="关系实例" note={`${draft.material_links.filter((item) => item.type_id === type.id).length} 条文档实例`} />
      <ElementInstances key={`${type.id}:${editing ? "edit" : "read"}`} {...props} canBrowseDatabase={canBrowseDatabase} />
    </ContentBlock>}
    <EvidenceSection workspaceId={draft.workspace_id} evidence={type.evidence} />
  </div>;
}
