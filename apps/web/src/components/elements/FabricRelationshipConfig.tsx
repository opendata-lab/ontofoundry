import { Alert, Form, Input, Select, Switch, Typography } from "antd";
import { KeyRound, Link2 } from "lucide-react";
import type { DataJoin, LinkType, MappingTableJoin } from "../../api/types";
import { byId } from "../../lib/coreModel";
import { changeType, type PanelProps } from "../../lib/elementModel";
import { objectMapping, sourceColumns } from "../../lib/objectMapping";
import { joinProblem } from "../../lib/objectMappingEditing";
import { FormRow, SectionTitle } from "../layout";
import { KeyEditor } from "./LinkMappingPanel";

const { Text } = Typography;
type Side = "source" | "target";

/** Adapts Microsoft's relationship configuration groups to the shared inspector frame. */
export function FabricRelationshipConfig(props: PanelProps<LinkType> & {
  showBinding: boolean;
}) {
  const { draft, type, editing, showBinding } = props;
  const join = type.data_join;
  const source = byId(draft.object_types, type.source_type_id);
  const target = byId(draft.object_types, type.target_type_id);
  const sourceRecord = source ? objectMapping(draft, source) : null;
  const targetRecord = target ? objectMapping(draft, target) : null;
  const dataset = join?.kind === "mapping_table" ? byId(draft.datasets, join.dataset_id) : undefined;
  const update = (patch: Partial<LinkType>) => changeType(props, patch);
  const setJoin = (value: DataJoin | null) => update({ data_join: value });
  const mode = join?.kind ?? "none";
  const setMapping = (enabled: boolean) => {
    if (enabled) setJoin({
      kind: "mapping_table", dataset_id: "", source_columns: [] as unknown as [string], target_columns: [] as unknown as [string],
      source_key: { kind: "mapping_key" }, target_key: { kind: "mapping_key" },
    });
    else if (join?.kind === "mapping_table") setJoin(null);
  };
  const mappingRow = (side: Side) => {
    if (join?.kind !== "mapping_table") return null;
    const columnsKey = side === "source" ? "source_columns" : "target_columns";
    const keyKey = side === "source" ? "source_key" : "target_key";
    const object = side === "source" ? source : target;
    const key = join[keyKey];
    const keyName = key.kind === "mapping_key" ? "对象数据的键列" : key.property_ids.map((id) => byId(draft.properties, id)?.name ?? "未指定属性").join(" + ");
    return (
      <div className="grid min-w-0 grid-cols-2 items-start gap-3">
        <Select
          mode={dataset?.columns?.length ? "multiple" : "tags"}
          className="w-full"
          aria-label={`${side === "source" ? "来源" : "目标"}端映射表列`}
          placeholder={dataset ? "选择映射表列" : "请先选择映射表"}
          disabled={!editing || !dataset}
          value={join[columnsKey]}
          options={sourceColumns(dataset).map((column) => ({ value: column, label: column }))}
          onChange={(value: string[]) => setJoin({ ...join, [columnsKey]: value })}
        />
        <div className="flex min-w-0 items-start gap-2">
          <Link2 size={14} className="mt-2 shrink-0 text-muted" />
          {editing && object ? <div className="min-w-0 flex-1"><KeyEditor
            draft={draft} typeId={object.id} value={key} label={object.name}
            onChange={(value: MappingTableJoin["source_key"]) => setJoin({ ...join, [keyKey]: value })}
          /></div> : <span className="inline-flex min-h-control-sm min-w-0 items-center gap-2"><KeyRound size={14} className="shrink-0 text-muted" /><Text className="break-words">{keyName || "未指定键"}</Text></span>}
        </div>
      </div>
    );
  };
  const endpoint = (side: Side) => {
    return (
      <section className="flex min-w-0 flex-col gap-3">
        <Form.Item className="mb-0" label={`${side === "source" ? "来源" : "目标"}对象类型`} required>
          <Input aria-label={`${side === "source" ? "来源" : "目标"}对象`} readOnly value={(side === "source" ? source : target)?.name || "未指定对象"} />
        </Form.Item>
        <div className="grid grid-cols-2 gap-3 text-xs"><Text>映射表列</Text><Text>对象键属性</Text></div>
        {mappingRow(side)}
      </section>
    );
  };
  const problem = joinProblem(join);
  return (
    <Form layout="vertical" component="div" size="small" className="fabric-relationship-form flex w-full min-w-0 flex-col gap-3">
      <SectionTitle title="数据映射" />
      {showBinding && <FormRow>
        <Form.Item className="mb-0" label="使用映射表">
          <div className="flex min-h-control-sm items-center gap-3">
            <Switch size="small" aria-label="使用映射表" checked={mode === "mapping_table"} disabled={!editing} onChange={setMapping} />
            <Text type="secondary">{mode === "mapping_table" ? "已启用" : "未启用"}</Text>
          </div>
        </Form.Item>
      </FormRow>}
      {showBinding && join?.kind === "mapping_table" && <section className="flex min-w-0 flex-col gap-3 border-t border-rule pt-4">
        <SectionTitle title="映射表" />
        <FormRow>
          <Form.Item className="mb-0" label="数据集">
            {editing && join?.kind === "mapping_table" ? <Select
              className="w-full" aria-label="关系来源数据集" placeholder="选择已登记的数据集"
              showSearch optionFilterProp="label" value={join.dataset_id || undefined}
              options={draft.datasets.map((item) => ({ value: item.id, label: item.name }))}
              onChange={(dataset_id: string) => setJoin({ ...join, dataset_id, source_columns: [] as unknown as [string], target_columns: [] as unknown as [string] })}
            /> : <Input aria-label="关系来源数据集" readOnly value={dataset?.name ?? "未绑定"} />}
          </Form.Item>
        </FormRow>
        <FormRow>
          <Form.Item className="mb-0" label="物理表">
            <Text className="break-words">
              {dataset ? [dataset.schema_name, dataset.table_name].filter(Boolean).join(".") || "—" : "—"}
            </Text>
          </Form.Item>
        </FormRow>
      </section>}
      {showBinding && join?.kind === "mapping_table" && <>
        <section className="flex min-w-0 flex-col gap-3 border-t border-rule pt-4">
          <SectionTitle title="字段对应" />
          <FormRow>{endpoint("source")}{endpoint("target")}</FormRow>
        </section>
        {editing && problem && <Alert type="warning" showIcon message={problem} />}
        {(sourceRecord?.mode === "virtual" || targetRecord?.mode === "virtual") && <Alert type="info" showIcon message="虚拟父对象的关系绑定在具体子对象上配置。" />}
      </>}
    </Form>
  );
}
