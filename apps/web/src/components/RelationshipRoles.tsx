import type { ReactElement } from "react";
import type { LinkDefinition, RoleConcept } from "../api/types";
import type { ElementRequest } from "../lib/elementInspector";
import { ConceptTag } from "./ConceptTag";

const PLACEHOLDER = /\{([^{}:]+)(?::([^{}]+))?\}/g;

/** A reading with each `{concept}` / `{concept:role}` placeholder shown as its concept's tag. */
function Reading({
  text,
  roles,
  tag,
}: {
  text: string;
  roles: RoleConcept[];
  tag: (role: RoleConcept, label?: string) => ReactElement;
}) {
  const parts: (string | ReactElement)[] = [];
  let last = 0;
  for (const match of text.matchAll(PLACEHOLDER)) {
    const [whole, concept, roleName] = match;
    const role =
      roles.find(
        (r) =>
          r.concept === concept && (roleName ? r.name === roleName : !r.name),
      ) ?? roles.find((r) => r.concept === concept);
    parts.push(text.slice(last, match.index));
    parts.push(
      role ? <span key={match.index}>{tag(role, roleName)}</span> : whole,
    );
    last = match.index! + whole.length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

export function RelationshipRoles({
  link,
  compact = false,
  open,
  conceptName,
}: {
  link: LinkDefinition;
  compact?: boolean;
  open?: (request: ElementRequest) => void;
  conceptName?: (id: string) => string | undefined;
}) {
  const roles: RoleConcept[] = link.role_concepts ?? [
    {
      id: `owner:${link.id}`,
      name: link.owner_role_name,
      concept: link.owner_ref?.ref ?? "",
      kind: link.owner_ref?.kind ?? "object_type",
      ref: link.owner_ref?.ref,
    },
    ...(link.roles ?? []).map((r) => ({
      id: r.id,
      name: r.name,
      concept: r.concept.ref,
      kind: r.concept.kind,
      ref: r.concept.ref,
    })),
  ];
  const arity =
    roles.length === 1 ? "一元" : roles.length === 2 ? "二元" : "多元";
  const tag = (role: RoleConcept, roleName?: string | null) => {
    const name = (role.ref && conceptName?.(role.ref)) || role.concept;
    return (
      <ConceptTag
        label={roleName ? `${name}（${roleName}）` : name}
        kind={role.kind}
        id={role.ref}
        open={open}
      />
    );
  };
  if (compact)
    return (
      <p className="relationship-roles--compact">
        <span className="muted">{arity}</span>
        {roles.map((r) => (
          <span key={r.id}>{tag(r, r.name)}</span>
        ))}
      </p>
    );
  return (
    <div className="relationship-roles">
      {!compact && <h3>关系角色</h3>}
      <p className="muted">
        {arity}关系 · {roles.length} 个角色
      </p>
      <ol aria-label="有序角色列表">
        {roles.map((r, i) => (
          <li key={r.id}>
            {tag(r)}
            {r.name != null && (
              <span> · {r.name === "" ? "（空角色名）" : r.name}</span>
            )}
            <small>
              {i === 0 ? " · 所属概念（隐含角色）" : ""} ·{" "}
              {r.kind === "object_type"
                ? "实体"
                : r.kind === "value_type"
                  ? "值概念"
                  : r.kind === "any"
                    ? "Any"
                    : "内置值类型"}
            </small>
          </li>
        ))}
      </ol>
      {!compact && !!link.verbalizes?.length && (
        <div>
          <h4>语义描述</h4>
          <ul aria-label="原生语义描述">
            {link.verbalizes.map((reading, i) => (
              <li key={i} className="reading">
                <Reading text={reading} roles={roles} tag={tag} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
