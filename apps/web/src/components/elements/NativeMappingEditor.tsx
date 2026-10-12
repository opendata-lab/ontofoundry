import { useState } from "react";
import type {
  SemanticChange,
  SemanticConcept,
  SemanticConceptMapping,
} from "../../api/types";
import { isObject, type PanelProps } from "../../lib/elementModel";
import { HintIcon } from "../HintIcon";
import { MappingTreeEditor } from "../semantic/MappingTreeEditor";
import {
  SemanticObjectForm,
  type SemanticFormTarget,
} from "../semantic/SemanticObjectForm";
import { ConceptTag } from "../ConceptTag";
import "../../styles/semantic.css";
import { nativeSemanticModels, semanticLabel } from "../../lib/semanticEditing";

export function NativeMappingEditor(props: PanelProps) {
  const { nativeDraft, draft, type, editing, change, open } = props;
  const [form, setForm] = useState<SemanticFormTarget | null>(null);
  const [notice, setNotice] = useState("");
  const [modelId, setModelId] = useState("");
  const [roleId, setRoleId] = useState("");
  if (!nativeDraft)
    return <p className="muted">请重新读取完整语义模型后配置映射。</p>;
  const models = nativeSemanticModels(nativeDraft);
  const owner = isObject(type) ? type.id : type.owner_ref?.ref;
  const matching = models.filter((m) =>
    m.concept_mappings?.some((cm) => cm.concept_id.ref === owner),
  );
  const model =
    models.find((m) => m.id === modelId) ?? matching[0] ?? models[0];
  const concepts: SemanticConcept[] = [
    ...draft.object_types.map((c) => ({ ...c, kind: "object_type" as const })),
    ...(draft.value_types ?? []).map((c) => ({
      ...c,
      kind: "value_type" as const,
    })),
  ];
  if (!model)
    return (
      <section className="element-section">
        <h3>原生映射</h3>
        <p>请在数据映射 → 语义模型中添加数据集，再配置映射。</p>
      </section>
    );
  const applied = draft._semantic_changes ?? [];
  const apply = (value: SemanticChange) => {
    change({
      ...draft,
      _semantic_changes: [
        ...applied.filter((c) => !(c.id === value.id && c.kind === value.kind)),
        value,
      ],
    });
    setNotice("已应用到元素，点击卡片右上角保存发布");
    setForm(null);
  };
  const cmValues = (cm: SemanticConceptMapping) => {
    const pending = applied.find((c) => c.id === cm.id);
    return { ...cm, ...pending?.values, nodes: pending?.nodes ?? cm.nodes };
  };
  const cmList =
    model.concept_mappings?.filter((c) => c.concept_id.ref === owner) ?? [];
  const role = !isObject(type)
    ? (type.roles?.find((r) => r.id === roleId) ?? type.roles?.[0])
    : undefined;
  const datasetsFor = (conceptId?: string) =>
    model.datasets.filter((d) =>
      model.concept_mappings?.some(
        (cm) =>
          cm.concept_id.ref === conceptId &&
          cm.nodes.some((n) => n.expression?.includes(d.name + ".")),
      ),
    );
  const ownerDatasets = datasetsFor(owner),
    roleDatasets = datasetsFor(role?.concept.ref);
  const relationships =
    ownerDatasets.length && roleDatasets.length
      ? model.relationships.filter(
          (r) =>
            (ownerDatasets.some((d) => d.name === r.from) &&
              roleDatasets.some((d) => d.name === r.to)) ||
            (ownerDatasets.some((d) => d.name === r.to) &&
              roleDatasets.some((d) => d.name === r.from)),
        )
      : model.relationships;
  return (
    <section className="element-section native-mapping-editor">
      <div className="semantic-row">
        <h3>原生映射</h3>
        <HintIcon text="直接编辑 concept_mapping 的原生树，支持多根、多字段表达式与引用映射。实例查询能力由映射结构决定，编辑不受查询能力限制。" />
        {editing && !cmList.length && (
          <button
            type="button"
            onClick={() =>
              setForm({
                kind: "concept_mapping",
                operation: "create",
                id: crypto.randomUUID(),
                parent_id: model.id,
                original: {
                  concept_id: {
                    kind:
                      isObject(type) && type.concept_kind === "value_type"
                        ? "value_type"
                        : "object_type",
                    ref: owner,
                  },
                  nodes: [],
                },
              })
            }
          >
            新增概念映射
          </button>
        )}
      </div>
      <label>
        语义模型
        <select
          aria-label="映射语义模型"
          value={model.id}
          onChange={(e) => {
            setModelId(e.target.value);
            setForm(null);
          }}
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {semanticLabel(m)}
            </option>
          ))}
        </select>
      </label>
      {notice && <p role="status">{notice}</p>}
      {cmList.map((cm) => (
        <details key={cm.id} open>
          <summary>
            <ConceptTag
              kind={cm.concept_id.kind}
              id={cm.concept_id.ref}
              label={cm.concept?.name ?? "概念映射"}
              open={open}
            />{" "}
            · {cmValues(cm).nodes.length} 节点
          </summary>
          {editing && (
            <button
              type="button"
              onClick={() =>
                setForm({
                  kind: "concept_mapping",
                  operation: "update",
                  id: cm.id,
                  parent_id: model.id,
                  original: cmValues(cm),
                })
              }
            >
              编辑映射树
            </button>
          )}
          <MappingTreeEditor
            nodes={cmValues(cm).nodes}
            editing={false}
            concepts={concepts}
            onChange={() => {}}
          />
        </details>
      ))}
      {!isObject(type) && (
        <>
          <h3>
            数据集连接{" "}
            <HintIcon text="所属概念与各角色的数据集通过字段等值连接。支持多个连接键；字段必须已存在于相应数据集。" />
          </h3>
          <div className="semantic-chips" aria-label="按角色配置连接">
            {!isObject(type) &&
              type.roles?.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  aria-pressed={role?.id === r.id}
                  onClick={() => {
                    setRoleId(r.id);
                    setForm(null);
                  }}
                >
                  <ConceptTag
                    kind={r.concept.kind}
                    label={
                      (concepts.find((c) => c.id === r.concept.ref)?.name ??
                        r.concept.ref) + (r.name ? `（${r.name}）` : "")
                    }
                  />
                </button>
              ))}
          </div>
          <p className="muted">
            所属概念 → 附加角色
            {role && (
              <HintIcon
                text={`当前角色稳定 ID：${role.id}。换序后连接仍按概念映射匹配；不同角色的复合键分别保留。`}
              />
            )}
          </p>
          {relationships.map((rel) => {
            const pending = applied.find((c) => c.id === rel.id);
            const value = { ...rel, ...pending?.values };
            return (
              <details key={rel.id}>
                <summary>
                  {rel.name} · {rel.from} → {rel.to}
                </summary>
                {rel.from_columns.map((c, i) => (
                  <p key={i}>
                    <code>
                      {c} = {rel.to_columns[i]}
                    </code>
                  </p>
                ))}
                {editing && (
                  <button
                    type="button"
                    onClick={() =>
                      setForm({
                        kind: "dataset_relationship",
                        operation: "update",
                        id: rel.id,
                        parent_id: model.id,
                        original: value,
                      })
                    }
                  >
                    编辑复合连接
                  </button>
                )}
              </details>
            );
          })}
          {editing && (
            <button
              type="button"
              onClick={() =>
                setForm({
                  kind: "dataset_relationship",
                  operation: "create",
                  id: crypto.randomUUID(),
                  parent_id: model.id,
                  original: {
                    name:
                      type.technical_name +
                      (role ? "__" + role.id.replaceAll("-", "") : ""),
                    from: ownerDatasets[0]?.name ?? "",
                    to: roleDatasets[0]?.name ?? "",
                    from_columns: [""],
                    to_columns: [""],
                  },
                })
              }
            >
              新增数据集连接
            </button>
          )}
        </>
      )}
      {editing && form && (
        <SemanticObjectForm
          key={form.id}
          target={form}
          model={model}
          concepts={concepts}
          onSubmit={apply}
          submitLabel="应用到元素"
        />
      )}
    </section>
  );
}
