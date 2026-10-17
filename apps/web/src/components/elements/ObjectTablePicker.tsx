import { Alert, Button, Descriptions, Select, Tag, Typography } from "antd";
import { Plus, Trash2 } from "lucide-react";
import type { Dataset, Draft, ObjectType } from "../../api/types";
import { byId, remove, type ResolvedSource } from "../../lib/coreModel";
import { datasetLabel } from "../../lib/datasetEditing";
import { objectMapping, sourceColumns, sourceLabel } from "../../lib/objectMapping";
import {
  MAIN_SOURCE,
  addSource,
  removeSource,
  setKeyColumns,
  setMainDataset,
  setMembershipSource,
} from "../../lib/objectMappingEditing";
import { BINDING_MODES } from "../../lib/objectMapping";

const { Text } = Typography;


function KeyColumns({
  dataset,
  value,
  label,
  onChange,
}: {
  dataset: Dataset | undefined;
  value: string[];
  label: string;
  onChange?: (columns: string[]) => void;
}) {
  const columns = sourceColumns(dataset);
  return (
    <Select
      mode={columns.length ? "multiple" : "tags"}
      aria-label={label}
      disabled={!onChange || undefined}
      placeholder={columns.length ? "按顺序选择键列" : "未登记列清单，输入列名"}
      value={value}
      options={columns.map((c) => ({ value: c, label: c }))}
      onChange={onChange}
      className="min-w-[220px]"
    />
  );
}

/**
 * Where an object's instances come from. An independent mapping picks its
 * main dataset and side tables; a child of a bound parent shares the
 * parent's data and may add extension tables, one of which can limit members.
 */
export function MappingSources({
  draft,
  type,
  editing,
  change,
}: {
  draft: Draft;
  type: ObjectType;
  editing: boolean;
  change: (next: Draft) => void;
}) {
  const record = objectMapping(draft, type);
  const { mode, mapping } = record;
  const datasets = draft.datasets.map((d) => ({ value: d.id, label: datasetLabel(d) }));
  const membership = mapping?.membership_source_id ?? null;
  const inherited = record.sources.filter((s) => s.ownerTypeId !== type.id);
  const own = record.sources.filter((s) => s.ownerTypeId === type.id);
  const shared = mode === "shared_parent";
  if (!editing) {
    if (!record.sources.length)
      return (
        <Alert
          type="info"
          showIcon
          message={mode === "virtual" ? "虚拟父对象：实例来自各子对象，本对象不绑定数据集。" : "还没有绑定数据集。"}
        />
      );
    return (
      <Descriptions
        size="small"
        bordered
        column={1}
        items={[
          { key: "mode", label: "实例来源", children: BINDING_MODES[mode] },
          ...record.sources.map((s) => ({
            key: `${s.ownerTypeId}:${s.id}`,
            label: sourceLabel(s, membership),
            children: (
              <span className="flex flex-wrap items-center gap-2">
                {datasetLabel(s.dataset)}
                {s.key_columns.length > 0 && <Text type="secondary">键列：{s.key_columns.join(", ")}</Text>}
                {s.dataset?.snapshot_date_column && <Tag className="!m-0">每日快照</Tag>}
                {s.ownerTypeId !== type.id && (
                  <Text type="secondary">来自{byId(draft.object_types, s.ownerTypeId)?.name}</Text>
                )}
              </span>
            ),
          })),
        ]}
      />
    );
  }
  if (mode === "virtual")
    return <Alert type="info" showIcon message="子对象已各自绑定数据集，本对象作为虚拟父对象不绑定主表" />;
  if (!draft.datasets.length)
    return <Alert type="info" showIcon message="还没有登记数据集。请先在“数据映射 → 数据集”登记要使用的表或视图。" />;
  const main = own.find((s) => s.id === MAIN_SOURCE);
  const sides = own.filter((s) => s.id !== MAIN_SOURCE);
  const sourceRow = (s: ResolvedSource, title: string, removable: boolean) => (
    <div key={s.id} className="grid grid-cols-[96px_minmax(200px,1fr)_minmax(220px,1fr)_32px] items-center gap-2">
      <Text type="secondary">{title}</Text>
      <Select
        aria-label={`${title}数据集`}
        showSearch
        optionFilterProp="label"
        value={s.dataset_id}
        options={datasets}
        onChange={(datasetId: string) =>
          change(
            s.id === MAIN_SOURCE
              ? setMainDataset(draft, type.id, datasetId, [])
              : {
                  ...draft,
                  mappings: draft.mappings.map((m) =>
                    m.type_id === type.id
                      ? { ...m, sources: m.sources.map((x) => (x.id === s.id ? { ...x, dataset_id: datasetId, key_columns: [] } : x)) }
                      : m,
                  ),
                },
          )
        }
      />
      <KeyColumns
        dataset={s.dataset}
        label={`${title}键列`}
        value={s.key_columns}
        onChange={(columns) => change(setKeyColumns(draft, type.id, s.id, columns))}
      />
      {removable ? (
        <Button
          type="text"
          aria-label={`移除${title}`}
          icon={<Trash2 size={15} />}
          onClick={() => change(removeSource(draft, type.id, s.id))}
        />
      ) : (
        <span />
      )}
    </div>
  );
  return (
    <div className="flex flex-col gap-3">
      {shared && (
        <Alert
          type="info"
          showIcon
          message={`共用${byId(draft.object_types, inherited[0]?.ownerTypeId)?.name ?? "父对象"}的数据。用成员条件或成员扩展表限定哪些实例属于本对象。`}
        />
      )}
      {inherited.map((s) => (
        <div key={`${s.ownerTypeId}:${s.id}`} className="grid grid-cols-[96px_1fr] items-center gap-2">
          <Text type="secondary">{sourceLabel(s)}</Text>
          <Text>
            {datasetLabel(s.dataset)} <Text type="secondary">· 来自{byId(draft.object_types, s.ownerTypeId)?.name}</Text>
          </Text>
        </div>
      ))}
      {!shared &&
        (main ? (
          sourceRow(main, "主表", false)
        ) : (
          <div className="grid grid-cols-[96px_minmax(200px,1fr)] items-center gap-2">
            <Text type="secondary">主表</Text>
            <Select
              aria-label="主表数据集"
              showSearch
              optionFilterProp="label"
              placeholder="选择已登记的数据集"
              options={datasets}
              onChange={(datasetId: string) => change(setMainDataset(draft, type.id, datasetId, []))}
            />
          </div>
        ))}
      {sides.map((s) => sourceRow(s, shared ? "扩展表" : `附表 ${s.id}`, true))}
      <div className="flex flex-wrap items-center gap-3">
        {(shared || main) && (
          <Select
            aria-label={shared ? "添加扩展表" : "添加附表"}
            showSearch
            optionFilterProp="label"
            placeholder={
              <span className="inline-flex items-center gap-1">
                <Plus size={14} />
                {shared ? "添加扩展表" : "添加附表"}
              </span>
            }
            value={null}
            options={datasets}
            className="min-w-[240px]"
            onChange={(datasetId: string) => change(addSource(draft, type.id, datasetId).draft)}
          />
        )}
        {shared && sides.length > 0 && (
          <span className="inline-flex items-center gap-2">
            <Text type="secondary">成员扩展表</Text>
            <Select
              aria-label="成员扩展表"
              allowClear
              placeholder="不限定"
              className="min-w-[200px]"
              value={membership ?? undefined}
              options={sides.map((s) => ({ value: s.id, label: datasetLabel(s.dataset) }))}
              onChange={(sourceId?: string) => change(setMembershipSource(draft, type.id, sourceId ?? null))}
            />
          </span>
        )}
        {mapping && (
          <Button danger type="text" onClick={() => change(remove(draft, "mappings", mapping.id))}>
            解除本对象的数据绑定
          </Button>
        )}
      </div>
    </div>
  );
}
