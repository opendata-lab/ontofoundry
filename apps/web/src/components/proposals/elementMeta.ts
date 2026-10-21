import type { ProposalItem, ProposalStatus, TargetKind } from "../../api/types";

export const KIND: Record<TargetKind, { label: string; color: string }> = {
  object_type: { label: "对象", color: "blue" },
  property: { label: "属性", color: "green" },
  link_type: { label: "关系", color: "cyan" },
  rule: { label: "规则", color: "purple" },
  metric: { label: "指标", color: "magenta" },
  dataset: { label: "数据集", color: "geekblue" },
  mapping: { label: "映射", color: "orange" },
  material_object: { label: "文档实例", color: "gold" },
  material_link: { label: "关系实例", color: "gold" },
  value_type: { label: "值类型", color: "lime" },
};

export const OPERATION: Record<ProposalItem["operation"], string> = {
  create: "新增",
  update: "修改",
  delete: "删除",
};

export const STATUS: Record<ProposalStatus, string> = {
  pending: "待审",
  accepted: "已接受",
  rejected: "已拒绝",
  stale: "已过期",
  conflict: "冲突",
  superseded: "已被取代",
};

export const STATUS_COLOR: Record<ProposalStatus, string> = {
  pending: "default",
  accepted: "success",
  rejected: "default",
  stale: "warning",
  conflict: "error",
  superseded: "default",
};

/** Heading like "属性 · 供应商.信用等级". */
export function itemTitle(item: ProposalItem) {
  const name =
    item.target_kind === "property" && item.owner_label ? `${item.owner_label}.${item.display_name}` : item.display_name;
  return `${KIND[item.target_kind].label} · ${name}`;
}

/** Every pending item whose whole dependency group is pending too. */
export function acceptableIds(items: ProposalItem[]) {
  const byId = new Map(items.map((i) => [i.id, i]));
  return items
    .filter(
      (i) =>
        i.status === "pending" &&
        i.dependency_group.every((id) => {
          const dep = byId.get(id);
          return !dep || dep.status === "pending" || dep.status === "accepted";
        }),
    )
    .map((i) => i.id);
}

export const FIELD_LABELS: Record<string, string> = {
  display_name: "名称",
  name: "英文标识",
  description: "描述",
  synonyms: "同义词",
  tags: "标签",
  extends: "父对象",
  derived_by: "成员条件",
  title_property_id: "标题属性",
  value_kind: "值类型",
  required: "必填",
  unique: "唯一",
  identifier: "标识",
  multiplicity: "基数",
  verbalizes: "关系含义",
  source_role_name: "来源端角色名",
  target_role_name: "目标端角色名",
  data_join: "数据绑定",
  expression: "表达式",
  evidence: "证据",
  values: "属性值",
  owner_type_id: "所属对象",
  source_type_id: "来源对象",
  target_type_id: "目标对象",
  source_id: "来源实例",
  target_id: "目标实例",
  owner_kind: "归属类型",
  owner_id: "归属元素",
  rule_kind: "规则类型",
  type_id: "对象类型",
  kind: "计算方式",
  dataset_id: "数据集",
  aggregation: "聚合",
  measure: "度量列",
  filters: "条件",
  time_field: "时间字段",
  numerator_id: "分子",
  denominator_id: "分母",
  schema_name: "库 / schema",
  table_name: "表或视图",
  dialect: "数据库类型",
  snapshot_date_column: "快照日期列",
  columns: "列",
  binding_mode: "实例来源",
  sources: "来源",
  fields: "字段绑定",
  membership_source_id: "成员扩展表",
  inherited_link_bindings: "继承关系绑定",
  connection_id: "连接",
  source_kind: "来源方式",
  query_sql: "SQL",
};

export function fieldLabel(path: string): string {
  return FIELD_LABELS[path] ?? path;
}
