import {
  isObject,
  relationSource,
  relationTarget,
  type PanelProps,
} from "./elementModel";
import type { LinkTypeElement } from "../api/types";
import type { MappedRelation } from "./objectMapping";

export const relationDeleteReason =
  "现有元素保存接口要求关系继续存在，不能删除关系；请在「本体构建」中调整关系定义。";
export const relationCreateReason =
  "对象保存范围不包含新关系；请在「本体构建」中添加关系。";
export const mappingTableReason =
  "当前关系保存接口不能新建或替换映射表及其连接；请在「数据映射 › 语义模型 › 概念映射」中配置。";
export function relationEndpoints(
  props: PanelProps,
  definition: LinkTypeElement,
) {
  const sourceId = relationSource(definition);
  const targetId = relationTarget(definition);
  const source = props.draft.object_types.find((o) => o.id === sourceId);
  const target = props.draft.object_types.find((o) => o.id === targetId);
  return { sourceId, targetId, source, target };
}
export function relationEditReason(
  props: PanelProps,
  relation: MappedRelation,
) {
  if (relation.inherited) return "继承关系属于父对象，请编辑父对象。";
  if (isObject(props.type) && relation.incoming)
    return "入向关系的映射属于来源对象，请编辑来源对象。";
  if (isObject(props.type) && relation.definition.data_join)
    return "关联字段属于关系的保存范围，请打开关系单独编辑。";
  const entries = relation.branches.flatMap((b) => [
    ...b.source,
    ...b.roles.flatMap((r) => r.parts),
  ]);
  if (entries.some((e) => e.readonlyReason))
    return entries.find((e) => e.readonlyReason)!.readonlyReason!;
  if (
    props.nativeDraft &&
    !relation.definition.data_join &&
    entries.some((e) => !e.nodeId)
  )
    return "该关联字段来自表连接，当前弹窗不能修改表连接；请在「数据映射 › 语义模型 › 概念映射」中编辑。";
  if (props.nativeDraft && !relation.branches.length)
    return "关系尚无完整映射，当前弹窗不能创建关系映射树；请在「数据映射 › 语义模型 › 概念映射」中配置。";
  const { sourceId, targetId } = relationEndpoints(props, relation.definition);
  if (
    !relation.branches.length &&
    (!props.draft.mappings.some((m) => m.type_id === sourceId) ||
      !props.draft.mappings.some((m) => m.type_id === targetId))
  )
    return "请先完成来源对象与目标对象的单表映射，再配置关联字段。";
  return null;
}
