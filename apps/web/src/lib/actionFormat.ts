import type { ActionEffect, ValueKind } from "../api/types";
import { VALUE_KINDS } from "./coreModel";

export const ACTION_EFFECT_KINDS: Record<ActionEffect["kind"], string> = {
  set_property: "修改属性",
  add_link: "建立关系",
  remove_link: "解除关系",
  create_object: "创建实体",
};

export type ActionFieldLine = {
  key: string;
  prefix: string;
  refId?: string;
  targetLabel?: string;
  suffix: string;
};

type NamedObject = { id: string; name: string; display_name?: string | null };
type NamedProperty = NamedObject & { owner_type_id: string };
type NamedLink = NamedObject & { source_type_id: string; target_type_id: string };

export type ReferenceNameSource = {
  object_types?: NamedObject[];
  properties?: NamedProperty[];
  link_types?: NamedLink[];
};

/**
 * Enriches an id -> label map with qualified names for properties (`owner.property`)
 * and link types (`link（source → target）`) so rebinding between same-named targets
 * remains distinguishable in review and publish diffs.
 */
export function buildQualifiedReferenceNames(
  sources: ReferenceNameSource[],
  baseNames: Map<string, string>,
): Map<string, string> {
  const names = new Map(baseNames);
  const objects = new Map<string, string>();
  const properties = new Map<string, NamedProperty>();
  const links = new Map<string, NamedLink>();
  for (const source of sources) {
    for (const obj of source.object_types ?? []) {
      const label = obj.display_name || obj.name;
      if (label) {
        objects.set(obj.id, label);
        names.set(obj.id, label);
      }
    }
    for (const prop of source.properties ?? []) properties.set(prop.id, prop);
    for (const link of source.link_types ?? []) links.set(link.id, link);
  }
  const objectLabel = (id: string) => objects.get(id) ?? names.get(id);
  for (const prop of properties.values()) {
    const propLabel = prop.display_name || prop.name;
    const owner = objectLabel(prop.owner_type_id);
    if (propLabel) names.set(prop.id, owner ? `${owner}.${propLabel}` : propLabel);
  }
  for (const link of links.values()) {
    const linkLabel = link.display_name || link.name;
    const src = objectLabel(link.source_type_id);
    const tgt = objectLabel(link.target_type_id);
    if (linkLabel) names.set(link.id, src && tgt ? `${linkLabel}（${src} → ${tgt}）` : linkLabel);
  }
  return names;
}

function labelOf(id: unknown, names?: Map<string, string>): string {
  const key = typeof id === "string" ? id : "";
  if (!key) return "—";
  return names?.get(key) ?? key;
}

/** Structured lines for an action's parameter list, preserving value_type_id for UUID tooltips. */
export function parseActionParameters(value: unknown, names?: Map<string, string>): ActionFieldLine[] | null {
  if (!Array.isArray(value)) return null;
  if (value.length === 0) return [{ key: "empty", prefix: "（无参数）", suffix: "" }];
  const lines: ActionFieldLine[] = [];
  for (let i = 0; i < value.length; i++) {
    const item = value[i];
    if (!item || typeof item !== "object") return null;
    const param = item as Record<string, unknown>;
    const name = typeof param.name === "string" ? param.name : "";
    const display = typeof param.display_name === "string" && param.display_name ? param.display_name : "";
    const head = display && name ? `${display} (${name})` : display || name || "未命名参数";
    const kind = typeof param.value_kind === "string" ? VALUE_KINDS[param.value_kind as ValueKind] ?? param.value_kind : "";
    const req = param.required === false ? "可选" : "必填";
    const desc = typeof param.description === "string" && param.description.trim() ? ` — ${param.description.trim()}` : "";
    const vtId = typeof param.value_type_id === "string" && param.value_type_id ? param.value_type_id : undefined;
    if (vtId) {
      lines.push({
        key: `${name || i}:${vtId}`,
        prefix: `${head}：${kind ? `${kind} / ` : ""}值类型「`,
        refId: vtId,
        targetLabel: labelOf(vtId, names),
        suffix: `」（${req}）${desc}`,
      });
    } else {
      lines.push({
        key: `${name || i}`,
        prefix: `${head}${kind ? `：${kind}` : ""}（${req}）${desc}`,
        suffix: "",
      });
    }
  }
  return lines;
}

/** Structured lines for an action's declared effects, preserving target UUIDs for tooltips. */
export function parseActionEffects(value: unknown, names?: Map<string, string>): ActionFieldLine[] | null {
  if (!Array.isArray(value)) return null;
  if (value.length === 0) return [{ key: "empty", prefix: "（无声明效果）", suffix: "" }];
  const lines: ActionFieldLine[] = [];
  for (let i = 0; i < value.length; i++) {
    const item = value[i];
    if (!item || typeof item !== "object") return null;
    const eff = item as Record<string, unknown>;
    const kind = typeof eff.kind === "string" ? eff.kind : "";
    const kindLabel = ACTION_EFFECT_KINDS[kind as ActionEffect["kind"]] ?? kind;
    const rawRef =
      kind === "set_property"
        ? eff.property_id
        : kind === "add_link" || kind === "remove_link"
          ? eff.link_type_id
          : kind === "create_object"
            ? eff.object_type_id
            : undefined;
    const refId = typeof rawRef === "string" && rawRef ? rawRef : undefined;
    const desc = typeof eff.description === "string" && eff.description.trim() ? ` — ${eff.description.trim()}` : "";
    lines.push({
      key: `${kind}:${refId ?? i}`,
      prefix: `${kindLabel}：`,
      refId,
      targetLabel: labelOf(refId, names),
      suffix: desc,
    });
  }
  return lines;
}

/** Parses action structured fields (`parameters` / `effects`) into tooltip-ready lines. */
export function parseActionField(path: string, value: unknown, names?: Map<string, string>): ActionFieldLine[] | null {
  if (path === "parameters") return parseActionParameters(value, names);
  if (path === "effects") return parseActionEffects(value, names);
  return null;
}

function joinLines(lines: ActionFieldLine[] | null): string | null {
  return lines ? lines.map((line) => `${line.prefix}${line.targetLabel ?? ""}${line.suffix}`).join("\n") : null;
}

/** Human-readable multi-line summary of an action's parameter list. */
export function formatActionParameters(value: unknown, names?: Map<string, string>): string | null {
  return joinLines(parseActionParameters(value, names));
}

/** Human-readable multi-line summary of an action's declared effects list. */
export function formatActionEffects(value: unknown, names?: Map<string, string>): string | null {
  return joinLines(parseActionEffects(value, names));
}

/** Formats action structured fields (`parameters` / `effects`) for review and publish diffs. */
export function formatActionField(path: string, value: unknown, names?: Map<string, string>): string | null {
  return joinLines(parseActionField(path, value, names));
}
