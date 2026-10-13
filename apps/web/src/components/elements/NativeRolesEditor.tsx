import { useRef } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import type { ConceptRef, NativeRole, RoleConcept } from "../../api/types";
import { changeType, isObject, type PanelProps } from "../../lib/elementModel";
import { ConceptTag } from "../ConceptTag";
import { HintIcon } from "../HintIcon";
import { RelationshipRoles } from "../RelationshipRoles";
import { newId } from "../../lib/id";
import "../../styles/semantic.css";

const builtins = [
  "String",
  "Integer",
  "Decimal",
  "Float",
  "Boolean",
  "Date",
  "DateTime",
];
export function NativeRolesEditor(props: PanelProps) {
  const { type, draft, editing, open } = props;
  const textareas = useRef(new Map<number, HTMLTextAreaElement>());
  const focused = useRef(new Set<number>());
  if (isObject(type) || !type.owner_ref) return null;
  const concepts = [
    ...draft.object_types.map((c) => ({ ...c, kind: "object_type" as const })),
    ...(draft.value_types ?? []).map((c) => ({
      ...c,
      kind: "value_type" as const,
    })),
  ];
  const names = new Map(concepts.map((c) => [c.id, c.name]));
  const technical = (ref: ConceptRef) =>
    concepts.find((c) => c.id === ref.ref)?.technical_name ?? ref.ref;
  const roles = type.roles ?? [];
  const viewRoles: RoleConcept[] = [
    {
      id: type.owner_role_id ?? `owner:${type.id}`,
      name: type.owner_role_name,
      concept: technical(type.owner_ref),
      kind: type.owner_ref.kind,
      ref: type.owner_ref.ref,
    },
    ...roles.map((r) => ({
      id: r.id,
      name: r.name,
      concept: technical(r.concept),
      kind: r.concept.kind,
      ref: r.concept.ref,
    })),
  ];
  if (!editing)
    return (
      <section className="element-section">
        <RelationshipRoles
          link={{ ...type, role_concepts: viewRoles }}
          open={open}
          conceptName={(id) => names.get(id)}
        />
      </section>
    );
  const choices = (owner = false) => (
    <>
      <optgroup label="实体概念">
        {concepts
          .filter((c) => c.kind === "object_type")
          .map((c) => (
            <option key={c.id} value={`object_type:${c.id}`}>
              {c.name}
            </option>
          ))}
      </optgroup>
      <optgroup label="值概念">
        {concepts
          .filter((c) => c.kind === "value_type")
          .map((c) => (
            <option key={c.id} value={`value_type:${c.id}`}>
              {c.name}
            </option>
          ))}
      </optgroup>
      {!owner && (
        <>
          <optgroup label="内置类型">
            {builtins.map((name) => (
              <option key={name} value={`builtin:${name}`}>
                {name}
              </option>
            ))}
          </optgroup>
          <option value="any:Any">Any</option>
        </>
      )}
    </>
  );
  const parse = (value: string): ConceptRef => {
    const [kind, ref] = value.split(":");
    return { kind: kind as ConceptRef["kind"], ref };
  };
  const setRoles = (next: NativeRole[]) => changeType(props, { roles: next });
  const changeConcept = (
    old: ConceptRef,
    next: ConceptRef,
    name?: string | null,
  ) => {
    const previous = `{${technical(old)}${name ? ":" + name : ""}}`,
      after = `{${technical(next)}${name ? ":" + name : ""}}`;
    return (type.verbalizes ?? []).map((text) =>
      text.replaceAll(previous, after),
    );
  };
  const move = (index: number, direction: number) => {
    const next = [...roles];
    [next[index], next[index + direction]] = [
      next[index + direction],
      next[index],
    ];
    setRoles(next);
  };
  const updateName = (role: NativeRole, name: string) => {
    const old = `{${technical(role.concept)}${role.name ? ":" + role.name : ""}}`,
      next = `{${technical(role.concept)}${name ? ":" + name : ""}}`;
    changeType(props, {
      roles: roles.map((r) =>
        r.id === role.id ? { ...r, name: name || null } : r,
      ),
      verbalizes: (type.verbalizes ?? []).map((text) =>
        text.replaceAll(old, next),
      ),
    });
  };
  const allowed = new Set(
    viewRoles.map((r) => `${r.concept}${r.name ? ":" + r.name : ""}`),
  );
  return (
    <section className="element-section native-roles-editor">
      <div className="semantic-row">
        <h3>有序角色</h3>
        <HintIcon text="所属概念是隐含首角色，其后按原生顺序排列。角色名可空，不从显示名推断；相同概念的多个角色须明确命名。" />
        <span className="semantic-spacer" />
        <button
          type="button"
          onClick={() =>
            setRoles([
              ...roles,
              {
                id: newId(),
                concept: { kind: "builtin", ref: "String" },
                name: null,
                native_presence: [],
                origin: "platform",
              },
            ])
          }
        >
          <Plus size={12} />
          添加角色
        </button>
      </div>
      <div className="native-role-row">
        <small>0</small>
        <label>
          所属概念
          <select
            aria-label="所属概念"
            value={`${type.owner_ref.kind}:${type.owner_ref.ref}`}
            onChange={(e) => {
              const next = parse(e.target.value);
              changeType(props, {
                owner_ref: next,
                verbalizes: changeConcept(
                  type.owner_ref!,
                  next,
                  type.owner_role_name,
                ),
              });
            }}
          >
            {choices(true)}
          </select>
        </label>
        <span className="muted">隐含首角色</span>
        <ConceptTag
          kind={type.owner_ref.kind}
          label={names.get(type.owner_ref.ref) ?? technical(type.owner_ref)}
          id={type.owner_ref.ref}
          open={open}
        />
      </div>
      {roles.map((role, i) => (
        <div className="native-role-row" key={role.id}>
          <small>{i + 1}</small>
          <label>
            概念
            <select
              aria-label={`角色 ${i + 1} 概念`}
              value={`${role.concept.kind}:${role.concept.ref}`}
              onChange={(e) => {
                const next = parse(e.target.value);
                changeType(props, {
                  roles: roles.map((r) =>
                    r.id === role.id ? { ...r, concept: next } : r,
                  ),
                  verbalizes: changeConcept(role.concept, next, role.name),
                });
              }}
            >
              {choices()}
            </select>
          </label>
          <label>
            角色名
            <input
              aria-label={`角色 ${i + 1} 名称`}
              placeholder="可留空"
              value={role.name ?? ""}
              onChange={(e) => updateName(role, e.target.value)}
            />
          </label>
          <div className="semantic-actions">
            <button
              type="button"
              aria-label={`上移角色 ${i + 1}`}
              disabled={i === 0}
              onClick={() => move(i, -1)}
            >
              <ArrowUp size={12} />
            </button>
            <button
              type="button"
              aria-label={`下移角色 ${i + 1}`}
              disabled={i === roles.length - 1}
              onClick={() => move(i, 1)}
            >
              <ArrowDown size={12} />
            </button>
            <button
              type="button"
              aria-label={`删除角色 ${i + 1}`}
              onClick={() => setRoles(roles.filter((r) => r.id !== role.id))}
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
      ))}
      <div className="semantic-columns">
        <label>
          多重性
          <select
            aria-label="原生多重性"
            value={type.native_multiplicity ?? ""}
            onChange={(e) =>
              changeType(props, {
                native_multiplicity:
                  (e.target.value as "ManyToOne" | "OneToOne") || null,
              })
            }
          >
            <option value="">未声明</option>
            <option value="OneToOne">一对一</option>
            <option value="ManyToOne">多对一</option>
          </select>
        </label>
        <label className="element-checkbox">
          <input
            type="checkbox"
            checked={!!type.identifier}
            onChange={(e) =>
              changeType(props, { identifier: e.target.checked })
            }
          />
          此关系用作标识
        </label>
      </div>
      <div className="element-section-title">
        <h3>语义描述</h3>
        <HintIcon text="用概念技术名作为占位符：{concept}；有角色名时用 {concept:role_name}。保存前校验未知占位符，表达式不截断。" />
        <button
          type="button"
          onClick={() =>
            changeType(props, { verbalizes: [...(type.verbalizes ?? []), ""] })
          }
        >
          <Plus size={12} />
          添加语义描述
        </button>
      </div>
      {(type.verbalizes ?? []).map((text, i) => {
        const unknown = [...text.matchAll(/\{([^{}]+)\}/g)]
          .map((m) => m[1])
          .filter((p) => !allowed.has(p));
        return (
          <div className="native-description" key={i}>
            <div className="semantic-row">
              <span>语义描述 {i + 1}</span>
              <span className="semantic-spacer" />
              <button
                type="button"
                aria-label={`删除语义描述 ${i + 1}`}
                onClick={() =>
                  changeType(props, {
                    verbalizes: type.verbalizes?.filter((_, j) => i !== j),
                  })
                }
              >
                <Trash2 size={12} />
              </button>
            </div>
            <textarea
              aria-label={`语义描述 ${i + 1}`}
              rows={2}
              value={text}
              ref={(el) => {
                if (el) textareas.current.set(i, el);
                else textareas.current.delete(i);
                el?.setCustomValidity(
                  unknown.length ? `未知占位符：${unknown.join("、")}` : "",
                );
              }}
              onFocus={() => focused.current.add(i)}
              onChange={(e) =>
                changeType(props, {
                  verbalizes: type.verbalizes?.map((v, j) =>
                    i === j ? e.target.value : v,
                  ),
                })
              }
            />
            {unknown.length > 0 && (
              <p className="inline-error" role="alert">
                未知占位符：{unknown.join("、")}
              </p>
            )}
            <div className="semantic-chips">
              {viewRoles.map((r) => (
                <ConceptTag
                  key={r.id}
                  kind={r.kind}
                  label={
                    r.name
                      ? `${names.get(r.ref ?? "") ?? r.concept}（${r.name}）`
                      : (names.get(r.ref ?? "") ?? r.concept)
                  }
                  onSelect={() => {
                    const input = textareas.current.get(i);
                    const token = `{${r.concept}${r.name ? ":" + r.name : ""}}`;
                    const start =
                      input && focused.current.has(i)
                        ? input.selectionStart
                        : text.length;
                    const end =
                      input && focused.current.has(i)
                        ? input.selectionEnd
                        : text.length;
                    changeType(props, {
                      verbalizes: type.verbalizes?.map((v, j) =>
                        i === j ? v.slice(0, start) + token + v.slice(end) : v,
                      ),
                    });
                    requestAnimationFrame(() => {
                      if (input?.isConnected) {
                        input.focus();
                        input.setSelectionRange(
                          start + token.length,
                          start + token.length,
                        );
                      }
                    });
                  }}
                />
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
