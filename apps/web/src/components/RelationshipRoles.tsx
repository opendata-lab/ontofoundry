import type { LinkDefinition } from "../api/types";

export function RelationshipRoles({ link, compact = false }: { link: LinkDefinition; compact?: boolean }) {
  const roles = link.role_concepts ?? [
    { id: `owner:${link.id}`, name: link.owner_role_name, concept: link.owner_ref?.ref ?? "", kind: link.owner_ref?.kind ?? "object_type" },
    ...(link.roles ?? []).map(r => ({ id: r.id, name: r.name, concept: r.concept.ref, kind: r.concept.kind })),
  ];
  const arity = roles.length === 1 ? "一元" : roles.length === 2 ? "二元" : "多元";
  return <div className={`relationship-roles${compact ? " relationship-roles--compact" : ""}`}>
    {!compact && <h3>关系角色</h3>}
    <p className="muted">{arity}关系 · {roles.length} 个角色{compact ? " · 暂只读" : ""}</p>
    <ol aria-label="有序角色列表">
      {roles.map((r, i) => <li key={r.id}>
        <span>{r.concept}</span>{r.name != null && <span> · {r.name === "" ? "（空角色名）" : r.name}</span>}
        <small>{i === 0 ? " · 所属概念（隐含角色）" : ""} · {r.kind === "object_type" ? "实体" : r.kind === "value_type" ? "值概念" : r.kind === "any" ? "Any" : "内置值类型"}</small>
      </li>)}
    </ol>
    {!compact && !!link.verbalizes?.length && <div><h4>语义描述</h4><ul aria-label="原生语义描述">{link.verbalizes.map((reading, i) => <li key={i}><code>{reading}</code></li>)}</ul></div>}
  </div>;
}
