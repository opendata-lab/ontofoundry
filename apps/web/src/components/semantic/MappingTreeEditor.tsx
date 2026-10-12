import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import type { ConceptRef, MappingNode, SemanticConcept } from "../../api/types";
import { ConceptTag } from "../ConceptTag";
import { HintIcon } from "../HintIcon";

export function MappingTreeEditor({
  nodes,
  onChange,
  concepts,
  editing = true,
}: {
  nodes: MappingNode[];
  onChange: (nodes: MappingNode[]) => void;
  concepts: SemanticConcept[];
  editing?: boolean;
}) {
  const update = (id: string, patch: Partial<MappingNode>) =>
    onChange(nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  const add = (parent: MappingNode | null, slot: MappingNode["slot"]) => {
    const kind =
      slot === "children" || slot === "link_mappings"
        ? "link"
        : slot === "referent_mappings"
          ? "referent"
          : "object";
    onChange([
      ...nodes,
      {
        id: crypto.randomUUID(),
        parent_id: parent?.id ?? null,
        slot,
        kind,
        relationship: kind === "object" ? null : "",
        concept: null,
        expression: kind === "link" ? null : "",
      },
    ]);
  };
  const remove = (id: string) => {
    const ids = new Set([id]);
    let size = 0;
    while (size !== ids.size) {
      size = ids.size;
      for (const n of nodes)
        if (n.parent_id && ids.has(n.parent_id)) ids.add(n.id);
    }
    onChange(nodes.filter((n) => !ids.has(n.id)));
  };
  const move = (node: MappingNode, direction: number) => {
    const siblings = nodes.filter(
      (n) => n.parent_id === node.parent_id && n.slot === node.slot,
    );
    const other =
      siblings[siblings.findIndex((n) => n.id === node.id) + direction];
    if (!other) return;
    const next = [...nodes],
      a = next.indexOf(node),
      b = next.indexOf(other);
    [next[a], next[b]] = [next[b], next[a]];
    onChange(next);
  };
  const render = (parent: string | null): React.ReactNode =>
    nodes
      .filter((n) => n.parent_id === parent)
      .map((n) => (
        <div className="mapping-tree-node" key={n.id}>
          <div className="semantic-row">
            <strong>
              {n.kind === "object"
                ? "对象映射"
                : n.kind === "link"
                  ? "关系映射"
                  : "引用映射"}
            </strong>
            <small>{n.slot}</small>
            {editing && (
              <span className="semantic-actions">
                <button
                  type="button"
                  aria-label="上移映射节点"
                  onClick={() => move(n, -1)}
                >
                  <ArrowUp size={12} />
                </button>
                <button
                  type="button"
                  aria-label="下移映射节点"
                  onClick={() => move(n, 1)}
                >
                  <ArrowDown size={12} />
                </button>
                <button
                  type="button"
                  aria-label="删除映射节点及子节点"
                  onClick={() => remove(n.id)}
                >
                  <Trash2 size={12} />
                </button>
              </span>
            )}
          </div>
          {n.kind !== "object" && (
            <label>
              关系技术名
              {editing ? (
                <input
                  aria-label="映射关系技术名"
                  value={n.relationship ?? ""}
                  onChange={(e) =>
                    update(n.id, { relationship: e.target.value })
                  }
                />
              ) : (
                <code>{n.relationship}</code>
              )}
            </label>
          )}
          {n.kind === "object" && (
            <label>
              概念
              {editing ? (
                <select
                  aria-label="映射节点概念"
                  value={n.concept?.ref ?? ""}
                  onChange={(e) => {
                    const c = concepts.find((c) => c.id === e.target.value);
                    update(n.id, {
                      concept: c
                        ? ({
                            kind: c.kind ?? "object_type",
                            ref: c.id,
                          } as ConceptRef)
                        : null,
                    });
                  }}
                >
                  <option value="">沿用所属概念</option>
                  {concepts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              ) : (
                n.concept && (
                  <ConceptTag
                    kind={n.concept.kind}
                    label={
                      concepts.find((c) => c.id === n.concept?.ref)?.name ??
                      n.concept.ref
                    }
                  />
                )
              )}
            </label>
          )}
          {n.kind !== "link" && (
            <label>
              表达式
              {editing ? (
                <textarea
                  aria-label="映射表达式"
                  rows={2}
                  value={n.expression ?? ""}
                  onChange={(e) => update(n.id, { expression: e.target.value })}
                  placeholder="dataset.field / 计算表达式"
                />
              ) : (
                <pre>{n.expression || "—"}</pre>
              )}
            </label>
          )}
          {render(n.id)}
          {editing && (
            <div className="semantic-actions">
              {(n.kind === "object"
                ? ["children"]
                : n.kind === "link"
                  ? ["object_mapping", "referent_mappings"]
                  : ([] as MappingNode["slot"][])
              ).map((slot) => (
                <button
                  key={slot}
                  type="button"
                  onClick={() => add(n, slot as MappingNode["slot"])}
                >
                  <Plus size={12} />
                  {slot === "children"
                    ? "子关系"
                    : slot === "object_mapping"
                      ? "对象映射"
                      : "引用映射"}
                </button>
              ))}
            </div>
          )}
        </div>
      ));
  return (
    <div className="mapping-tree">
      <div className="semantic-row">
        <strong>映射树</strong>
        <HintIcon text="按原生树编辑多根、计算表达式和引用映射。删除节点同时移除其子树；其他分支与稳定 ID 保留。" />
        {editing && (
          <span className="semantic-actions">
            <button type="button" onClick={() => add(null, "object_mappings")}>
              <Plus size={12} />
              对象根
            </button>
            <button type="button" onClick={() => add(null, "link_mappings")}>
              <Plus size={12} />
              关系根
            </button>
          </span>
        )}
      </div>
      {render(null)}
      {!nodes.length && <p className="muted">尚无映射节点</p>}
    </div>
  );
}
