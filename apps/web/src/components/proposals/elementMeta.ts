import {
  Box,
  Braces,
  Database,
  FileText,
  GitBranch,
  Link2,
  ShieldCheck,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { ProposalItem, ProposalStatus, TargetKind } from "../../api/types";

export const KIND: Record<TargetKind, { label: string; icon: LucideIcon; cls: string }> = {
  object_type: { label: "实体", icon: Box, cls: "object" },
  property: { label: "属性", icon: Braces, cls: "attribute" },
  link_type: { label: "关系", icon: GitBranch, cls: "relation" },
  rule: { label: "规则", icon: ShieldCheck, cls: "rule" },
  action: { label: "Action", icon: Zap, cls: "action" },
  material_object: { label: "材料实例", icon: FileText, cls: "instance" },
  material_link: { label: "材料关系", icon: Link2, cls: "instance" },
  mapping: { label: "映射", icon: Database, cls: "mapping" },
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

/** Heading like "修改 属性 · 供应商.信用等级". */
export function itemTitle(item: ProposalItem) {
  const name =
    item.target_kind === "property" && item.owner_label
      ? `${item.owner_label}.${item.display_name}`
      : item.display_name;
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
