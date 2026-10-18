import { Alert, Button, Descriptions, Form, Segmented, Select, Typography } from "antd";
import { Plus, Trash2 } from "lucide-react";
import type { DataJoin, Draft, LinkType, MappingTableJoin, UUID } from "../../api/types";
import { bindingMode, byId, effectiveProperties, joinSummary } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { sourceColumns } from "../../lib/objectMapping";
import { joinProblem, setLinkJoin } from "../../lib/objectMappingEditing";

const { Text } = Typography;

type Key = MappingTableJoin["source_key"];


function KeyEditor({
  draft,
  typeId,
  value,
  label,
  onChange,
}: {
  draft: Draft;
  typeId: UUID;
  value: Key;
  label: string;
  onChange: (key: Key) => void;
}) {
  const properties = effectiveProperties(draft, typeId).map((p) => ({ value: p.definition.id, label: p.definition.name }));
  return (
    <div className="flex flex-col gap-2">
      <Select
        aria-label={`${label}对应方式`}
        value={value.kind}
        onChange={(kind: Key["kind"]) => onChange(kind === "mapping_key" ? { kind } : { kind, property_ids: [] as unknown as [string] })}
        options={[
          { value: "mapping_key", label: "对象数据的键列" },
          { value: "properties", label: "指定属性" },
        ]}
      />
      {value.kind === "properties" && (
        <Select
          mode="multiple"
          aria-label={`${label}对应属性`}
          placeholder="按顺序选择属性"
          value={value.property_ids}
          options={properties}
          optionFilterProp="label"
          onChange={(ids: string[]) => onChange({ kind: "properties", property_ids: ids as [string, ...string[]] })}
        />
      )}
    </div>
  );
}

/**
 * Edits a relation's data binding: matching properties of both ends, or a
 * registered mapping dataset. Endpoints are the effective types, so a child
 * binding an inherited relation uses its own (inherited) properties.
 */
export function LinkJoinEditor({
  draft,
  sourceTypeId,
  targetTypeId,
  value,
  onChange,
}: {
  draft: Draft;
  sourceTypeId: UUID;
  targetTypeId: UUID;
  value: DataJoin | null;
  onChange: (join: DataJoin | null) => void;
}) {
  const source = byId(draft.object_types, sourceTypeId);
  const target = byId(draft.object_types, targetTypeId);
  const options = (typeId: UUID) =>
    effectiveProperties(draft, typeId).map((p) => ({ value: p.definition.id, label: p.definition.name }));
  const mode = value?.kind ?? "none";
  const setMode = (next: string) => {
    if (next === mode) return;
    if (next === "none") onChange(null);
    else if (next === "direct")
      onChange({ kind: "direct", source_property_ids: [""], target_property_ids: [""] });
    else
      onChange({
        kind: "mapping_table",
        dataset_id: "",
        source_columns: [] as unknown as [string],
        target_columns: [] as unknown as [string],
        source_key: { kind: "mapping_key" },
        target_key: { kind: "mapping_key" },
      });
  };
  const problem = joinProblem(value);
  return (
    <Form layout="vertical" component="div" className="flex max-w-settings flex-col">
      <Form.Item label="绑定方式">
        <Segmented
          value={mode}
          onChange={(v) => setMode(String(v))}
          options={[
            { value: "none", label: "未绑定" },
            { value: "direct", label: "属性对应" },
            { value: "mapping_table", label: "映射表" },
          ]}
        />
      </Form.Item>
      {value?.kind === "direct" && (
        <Form.Item label={`${source?.name ?? "来源"} 的属性 = ${target?.name ?? "目标"} 的属性`}>
          <div className="flex flex-col gap-2">
            {value.source_property_ids.map((sourceId, i) => (
              <div key={i} className="flex items-center gap-2">
                <Select
                  className="min-w-0 flex-1"
                  aria-label={`第 ${i + 1} 组来源属性`}
                  showSearch
                  optionFilterProp="label"
                  value={sourceId || undefined}
                  options={options(sourceTypeId)}
                  onChange={(id: string) => {
                    const ids = [...value.source_property_ids];
                    ids[i] = id;
                    onChange({ ...value, source_property_ids: ids as [string, ...string[]] });
                  }}
                />
                <Text type="secondary">=</Text>
                <Select
                  className="min-w-0 flex-1"
                  aria-label={`第 ${i + 1} 组目标属性`}
                  showSearch
                  optionFilterProp="label"
                  value={value.target_property_ids[i] || undefined}
                  options={options(targetTypeId)}
                  onChange={(id: string) => {
                    const ids = [...value.target_property_ids];
                    ids[i] = id;
                    onChange({ ...value, target_property_ids: ids as [string, ...string[]] });
                  }}
                />
                <Button
                  type="text"
                  aria-label={`删除第 ${i + 1} 组对应`}
                  disabled={value.source_property_ids.length === 1 || undefined}
                  icon={<Trash2 size={15} />}
                  onClick={() =>
                    onChange({
                      ...value,
                      source_property_ids: value.source_property_ids.filter((_, j) => j !== i) as [string, ...string[]],
                      target_property_ids: value.target_property_ids.filter((_, j) => j !== i) as [string, ...string[]],
                    })
                  }
                />
              </div>
            ))}
            <Button
              type="dashed"
              size="small"
              icon={<Plus size={14} />}
              className="self-start"
              onClick={() =>
                onChange({
                  ...value,
                  source_property_ids: [...value.source_property_ids, ""],
                  target_property_ids: [...value.target_property_ids, ""],
                })
              }
            >
              添加一组对应
            </Button>
          </div>
        </Form.Item>
      )}
      {value?.kind === "mapping_table" && (
        <MappingTableFields
          draft={draft}
          value={value}
          onChange={onChange}
          ends={[
            { typeId: sourceTypeId, label: source?.name ?? "来源对象", side: "source" },
            { typeId: targetTypeId, label: target?.name ?? "目标对象", side: "target" },
          ]}
        />
      )}
      {problem && <Alert type="warning" showIcon message={problem} />}
    </Form>
  );
}

function MappingTableFields({
  draft,
  value,
  onChange,
  ends,
}: {
  draft: Draft;
  value: MappingTableJoin;
  onChange: (join: MappingTableJoin) => void;
  ends: { typeId: UUID; label: string; side: "source" | "target" }[];
}) {
  const dataset = byId(draft.datasets, value.dataset_id);
  const columns = sourceColumns(dataset).map((c) => ({ value: c, label: c }));
  return (
    <>
      <Form.Item label="映射表" extra={draft.datasets.length ? undefined : "还没有登记数据集，请先在数据映射页登记。"}>
        <Select
          aria-label="映射表"
          showSearch
          optionFilterProp="label"
          value={value.dataset_id || undefined}
          options={draft.datasets.map((d) => ({ value: d.id, label: d.name }))}
          onChange={(dataset_id: string) => onChange({ ...value, dataset_id })}
        />
      </Form.Item>
      <div className="grid grid-cols-2 gap-x-4">
        {ends.map(({ typeId, label, side }) => {
          const columnsKey = side === "source" ? "source_columns" : "target_columns";
          const keyKey = side === "source" ? "source_key" : "target_key";
          return (
            <Form.Item key={side} label={`${label}一端`}>
              <div className="flex flex-col gap-2">
                <Select
                  mode={columns.length ? "multiple" : "tags"}
                  aria-label={`${label}一端的列`}
                  placeholder={columns.length ? "选择映射表的列" : "数据集未登记列清单，输入列名"}
                  value={value[columnsKey]}
                  options={columns}
                  onChange={(next: string[]) => onChange({ ...value, [columnsKey]: next })}
                />
                <KeyEditor
                  draft={draft}
                  typeId={typeId}
                  label={label}
                  value={value[keyKey]}
                  onChange={(key) => onChange({ ...value, [keyKey]: key })}
                />
              </div>
            </Form.Item>
          );
        })}
      </div>
    </>
  );
}

/** The relation's own data binding (its data_join). */
export function LinkMappingPanel(props: PanelProps<LinkType>) {
  const { draft, type, editing, change } = props;
  const hasVirtualEndpoint =
    bindingMode(draft, type.source_type_id) === "virtual" ||
    bindingMode(draft, type.target_type_id) === "virtual";
  const virtualAlert = hasVirtualEndpoint ? (
    <Alert
      type="info"
      showIcon
      message="端点包含虚拟父对象：这条关系的数据绑定在各具体子对象的「关系」页分别配置，关系本身可不绑定。"
    />
  ) : null;
  if (!editing)
    return (
      <div className="flex max-w-settings flex-col gap-3">
        {virtualAlert}
        <Descriptions
          size="small"
          column={1}
          items={[
            { key: "join", label: "数据绑定", children: joinSummary(draft, type.data_join) },
            ...(type.data_join?.kind === "mapping_table"
              ? [
                  { key: "source", label: "来源端列", children: type.data_join.source_columns.join(", ") },
                  { key: "target", label: "目标端列", children: type.data_join.target_columns.join(", ") },
                ]
              : []),
          ]}
        />
      </div>
    );
  return (
    <div className="flex max-w-settings flex-col gap-3">
      {virtualAlert}
      <LinkJoinEditor
        draft={draft}
        sourceTypeId={type.source_type_id}
        targetTypeId={type.target_type_id}
        value={type.data_join}
        onChange={(join) => change(setLinkJoin(draft, type.id, join))}
      />
    </div>
  );
}
