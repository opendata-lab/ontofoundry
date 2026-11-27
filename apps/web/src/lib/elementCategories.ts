import { Box, Braces, Database, FileText, GitBranch, ShieldCheck, Sigma, TableProperties, Workflow, Zap, type LucideIcon } from "lucide-react";
import type { TargetKind } from "../api/types";

export type ElementCategory = { key: TargetKind; text: string; icon: LucideIcon; tone: string; background: string };

/** Element kinds in reading order: types and relations first, sources and instances last. */
export const ELEMENT_CATEGORIES: ElementCategory[] = [
  { key: "object_type", text: "实体", icon: Box, tone: "text-object", background: "bg-object-soft" },
  { key: "link_type", text: "关系", icon: GitBranch, tone: "text-relation", background: "bg-relation-soft" },
  { key: "property", text: "属性", icon: Braces, tone: "text-attribute", background: "bg-attribute-soft" },
  { key: "rule", text: "规则", icon: ShieldCheck, tone: "text-ink-2", background: "bg-canvas" },
  { key: "metric", text: "指标", icon: Sigma, tone: "text-ink-2", background: "bg-canvas" },
  { key: "action", text: "动作", icon: Zap, tone: "text-ink-2", background: "bg-canvas" },
  { key: "dataset", text: "数据集", icon: Database, tone: "text-ink-2", background: "bg-canvas" },
  { key: "mapping", text: "映射", icon: TableProperties, tone: "text-ink-2", background: "bg-canvas" },
  { key: "material_object", text: "文档实例", icon: FileText, tone: "text-ink-2", background: "bg-canvas" },
  { key: "material_link", text: "关系实例", icon: Workflow, tone: "text-ink-2", background: "bg-canvas" },
];
