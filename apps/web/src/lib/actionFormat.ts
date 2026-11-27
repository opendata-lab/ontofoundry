import type { ActionEffect, ValueKind } from "../api/types";
import { VALUE_KINDS } from "./coreModel";

export const ACTION_EFFECT_KINDS: Record<ActionEffect["kind"], string> = {
  set_property: "修改属性",
  add_link: "建立关系",
  remove_link: "解除关系",
  create_object: "创建实体",
};

function labelOf(id: unknown, names?: Map<string, string>): string {
  const key = typeof id === "string" ? id : "";
  if (!key) return "—";
  return names?.get(key) ?? key;
}

/** Human-readable multi-line summary of an action's parameter list. */
export function formatActionParameters(value: unknown, names?: Map<string, string>): string | null {
  if (!Array.isArray(value)) return null;
  if (value.length === 0) return "（无参数）";
  const lines: string[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const param = item as Record<string, unknown>;
    const name = typeof param.name === "string" ? param.name : "";
    const display = typeof param.display_name === "string" && param.display_name ? param.display_name : "";
    const head = display && name ? `${display} (${name})` : display || name || "未命名参数";
    const kind = typeof param.value_kind === "string" ? VALUE_KINDS[param.value_kind as ValueKind] ?? param.value_kind : "";
    const vt = typeof param.value_type_id === "string" && param.value_type_id ? `值类型「${labelOf(param.value_type_id, names)}」` : "";
    const typeText = [kind, vt].filter(Boolean).join(" / ");
    const req = param.required === false ? "可选" : "必填";
    const desc = typeof param.description === "string" && param.description.trim() ? ` — ${param.description.trim()}` : "";
    lines.push(`${head}${typeText ? `：${typeText}` : ""}（${req}）${desc}`);
  }
  return lines.join("\n");
}

/** Human-readable multi-line summary of an action's declared effects list. */
export function formatActionEffects(value: unknown, names?: Map<string, string>): string | null {
  if (!Array.isArray(value)) return null;
  if (value.length === 0) return "（无声明效果）";
  const lines: string[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const eff = item as Record<string, unknown>;
    const kind = typeof eff.kind === "string" ? eff.kind : "";
    const kindLabel = ACTION_EFFECT_KINDS[kind as ActionEffect["kind"]] ?? kind;
    const refId =
      kind === "set_property"
        ? eff.property_id
        : kind === "add_link" || kind === "remove_link"
          ? eff.link_type_id
          : kind === "create_object"
            ? eff.object_type_id
            : undefined;
    const target = labelOf(refId, names);
    const desc = typeof eff.description === "string" && eff.description.trim() ? ` — ${eff.description.trim()}` : "";
    lines.push(`${kindLabel}：${target}${desc}`);
  }
  return lines.join("\n");
}

/** Formats action structured fields (`parameters` / `effects`) for review and publish diffs. */
export function formatActionField(path: string, value: unknown, names?: Map<string, string>): string | null {
  if (path === "parameters") return formatActionParameters(value, names);
  if (path === "effects") return formatActionEffects(value, names);
  return null;
}
