import { Form, Input, Select, Typography } from "antd";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import type { LinkType } from "../../api/types";
import { byId } from "../../lib/coreModel";
import { changeType, type PanelProps } from "../../lib/elementModel";
import { isForwardReading, readingEditorText, renderLinkReading, storedReading } from "../../lib/linkReadings";
import { FormRow, SectionTitle } from "../layout";
import { ElementLink } from "./ElementPanels";

const { Text } = Typography;

/** Presents both directions while storing only the existing multiplicity. */
export function RelationshipConnection(props: PanelProps<LinkType>) {
  const { draft, type, editing, open } = props;
  const update = (patch: Partial<LinkType>) => changeType(props, patch);
  const groupText = (forward: boolean) => (type.verbalizes ?? []).filter((reading) => isForwardReading(reading) === forward).map(readingEditorText).join("\n");
  const [forwardText, setForwardText] = useState(() => groupText(true));
  const [reverseText, setReverseText] = useState(() => groupText(false));
  const setReadings = (forward: boolean, text: string) => {
    (forward ? setForwardText : setReverseText)(text);
    const lines = (value: string) => value.split("\n").map((line) => storedReading(line.trim())).filter(Boolean);
    update({ verbalizes: [...lines(forward ? text : forwardText), ...lines(forward ? reverseText : text)] });
  };
  const source = byId(draft.object_types, type.source_type_id);
  const target = byId(draft.object_types, type.target_type_id);
  const options = draft.object_types.map((object) => ({ value: object.id, label: (object.display_name || object.name) || object.name }));
  const forwardMany = type.multiplicity === "many_to_many";
  const reverseMany = type.multiplicity !== "one_to_one";
  const endpoint = (reverse: boolean) => {
    const object = reverse ? target : source;
    return <Form.Item className="mb-0" label={reverse ? "目标对象" : "来源对象"} required={editing}>
      {editing ? <Select className="w-full" aria-label={reverse ? "目标对象" : "来源对象"} showSearch optionFilterProp="label" options={options} value={object?.id}
        onChange={(id: string) => update(reverse ? { target_type_id: id, data_join: null } : { source_type_id: id, data_join: null })} />
        : object ? <ElementLink onClick={() => open({ kind: "object_type", id: object.id })}>{(object.display_name || object.name)}</ElementLink> : <Text type="secondary">未指定对象</Text>}
    </Form.Item>;
  };
  const direction = (reverse: boolean) => {
    const from = reverse ? target : source;
    const to = reverse ? source : target;
    const many = reverse ? reverseMany : forwardMany;
    const role = reverse ? type.source_role_name : type.target_role_name;
    const readings = (type.verbalizes ?? []).filter((reading) => isForwardReading(reading) !== reverse);
    const meaningLabel = reverse ? "反向关系含义" : "正向关系含义";
    return <section className="flex min-w-0 flex-col gap-3" aria-label={reverse ? "反向关系" : "正向关系"}>
      <SectionTitle title={role || (reverse ? "反向关系" : "正向关系")} note={<span className="inline-flex flex-wrap items-center gap-2">{(from?.display_name || from?.name) || "未指定对象"}<ArrowRight className="size-icon-sm text-muted" />{(to?.display_name || to?.name) || "未指定对象"}</span>} />
      <div className="flex min-h-control-sm flex-wrap items-center gap-2">
        <Text>每个 {(from?.display_name || from?.name) || "对象"} {role ? "有" : "对应"}</Text>
        {editing ? <Select className="w-inspector-cardinality" aria-label={reverse ? "每个目标对应的来源数量" : "每个来源对应的目标数量"} value={many ? "many" : "one"}
          options={[
            { value: "one", label: "一个", disabled: reverse && forwardMany },
            { value: "many", label: "多个", disabled: !reverse && !reverseMany },
          ]}
          onChange={(count: string) => {
            const nextForward = reverse ? forwardMany : count === "many";
            const nextReverse = reverse ? count === "many" : reverseMany;
            update({ multiplicity: nextForward ? "many_to_many" : nextReverse ? "many_to_one" : "one_to_one" });
          }} /> : <Text strong>{many ? "多个" : "一个"}</Text>}
        <Text>{role || (to?.display_name || to?.name) || "对象"}</Text>
      </div>
      <Form.Item className="mb-0" label={meaningLabel}>
        {editing ? <Input.TextArea aria-label={meaningLabel} autoSize={{ minRows: 2, maxRows: 6 }}
          placeholder={reverse ? "{目标}与{来源}的业务联系" : "{来源}与{目标}的业务联系"}
          value={reverse ? reverseText : forwardText} onChange={(e) => setReadings(!reverse, e.target.value)} />
          : readings.length ? <div className="flex flex-col gap-2">{readings.map((reading, index) => <Text key={index} className="whitespace-pre-wrap">{renderLinkReading(draft, type, reading)}</Text>)}</div>
          : <Text type="secondary">未填写关系含义</Text>}
      </Form.Item>
      {editing && readings.length > 0 && <div className="flex flex-col gap-2">{readings.map((reading, index) => <Text type="secondary" key={index} className="text-xs whitespace-pre-wrap">{renderLinkReading(draft, type, reading)}</Text>)}</div>}
    </section>;
  };
  return <section className="flex min-w-0 flex-col gap-3">
    <SectionTitle title="关系详情" />
    <Form component="div" layout="vertical" size="small" className="fabric-relationship-form flex min-w-0 flex-col gap-4">
      <FormRow>{endpoint(false)}{endpoint(true)}</FormRow>
      {(editing || type.source_role_name || type.target_role_name) && <FormRow>{([false, true] as const).map((targetSide) => {
        const role = targetSide ? type.target_role_name : type.source_role_name;
        const label = targetSide ? "目标端角色名" : "来源端角色名";
        return <Form.Item key={label} className="mb-0" label={label}>
          {editing ? <Input aria-label={label} placeholder="填写此端在关系中的角色" maxLength={240} value={role ?? ""} onChange={(e) => update(targetSide ? { target_role_name: e.target.value || null } : { source_role_name: e.target.value || null })} /> : <Text type={role ? undefined : "secondary"}>{role || "未设置"}</Text>}
        </Form.Item>;
      })}</FormRow>}
      {editing && <Text type="secondary" className="text-xs">关系含义使用 {"{来源}"}、{"{目标}"} 代表两端参与者，一行一条完整句式。</Text>}
      <FormRow>{direction(false)}{direction(true)}</FormRow>
    </Form>
  </section>;
}
