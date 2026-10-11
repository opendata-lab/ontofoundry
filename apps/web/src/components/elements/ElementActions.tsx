import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { HintedHeading } from "../HintIcon";
import type { ActionElement } from "../../api/types";
import {
  inheritedProperties,
  isObject,
  VALUE_KINDS,
  type PanelProps,
} from "../../lib/elementModel";
import { EvidenceSection, Field } from "./ElementPanels";

const EFFECT_NAMES = {
  set_property: "设置属性",
  create_link: "创建关系",
  delete_link: "删除关系",
};

export function ActionsPanel({
  draft,
  type,
  editing,
  change,
  open,
}: PanelProps) {
  const object = isObject(type);
  const actions = draft.actions.filter((a) =>
    object
      ? a.input_type_id === type.id
      : a.effects.some((e) => e.link_type_id === type.id),
  );
  const properties = object
    ? [
        ...draft.properties.filter((p) => p.owner_type_id === type.id),
        ...inheritedProperties(draft, type).map((p) => p.property),
      ]
    : [];
  const canEdit = editing && object;
  const update = (id: string, patch: Partial<ActionElement>) =>
    change({
      ...draft,
      actions: draft.actions.map((a) => (a.id === id ? { ...a, ...patch } : a)),
    });
  const add = () => {
    const id = crypto.randomUUID();
    change({
      ...draft,
      actions: [
        ...draft.actions,
        {
          id,
          input_type_id: type.id,
          name: "新动作",
          technical_name: `action_${id.replaceAll("-", "").slice(0, 8)}`,
          description: "",
          parameters: [],
          precondition_rule_ids: [],
          effects: [],
          evidence: [],
        },
      ],
    });
  };
  return (
    <section className="element-section">
      <div className="element-section-title">
        <HintedHeading title="动作" hint="动作描述业务操作，当前不可执行。" />
        {canEdit && (
          <button type="button" className="element-text-button" onClick={add}>
            <Plus size={14} />
            新增动作
          </button>
        )}
      </div>
      {actions.map((action) => {
        const prefix = `动作 ${action.name}`;
        const availableRules = draft.rules.filter(
          (r) =>
            action.precondition_rule_ids.includes(r.id) ||
            (r.owner_kind === "action" && r.owner_id === action.id) ||
            (r.owner_kind === "object_type" && r.owner_id === type.id),
        );
        const changeParameter = (
          id: string,
          patch: Partial<ActionElement["parameters"][number]>,
        ) =>
          update(action.id, {
            parameters: action.parameters.map((p) =>
              p.id === id ? { ...p, ...patch } : p,
            ),
          });
        const changeEffect = (
          id: string,
          patch: Partial<ActionElement["effects"][number]>,
        ) =>
          update(action.id, {
            effects: action.effects.map((effect) =>
              effect.id === id ? { ...effect, ...patch } : effect,
            ),
          });
        return (
          <article
            className="element-rule"
            key={action.id}
            data-element-id={action.id}
          >
            <div className="element-section-title">
              {canEdit ? (
                <input
                  aria-label="动作名称"
                  required
                  value={action.name}
                  onChange={(e) => update(action.id, { name: e.target.value })}
                />
              ) : (
                <strong>{action.name}</strong>
              )}
              {canEdit && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`删除动作 ${action.name}`}
                  onClick={() =>
                    change({
                      ...draft,
                      actions: draft.actions.filter((a) => a.id !== action.id),
                      rules: draft.rules.filter(
                        (r) =>
                          !(
                            r.owner_kind === "action" &&
                            r.owner_id === action.id
                          ),
                      ),
                    })
                  }
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
            {canEdit ? (
              <>
                <Field label="英文名称">
                  <input
                    required
                    pattern="[A-Za-z_][A-Za-z0-9_]*"
                    value={action.technical_name}
                    onChange={(e) =>
                      update(action.id, { technical_name: e.target.value })
                    }
                  />
                </Field>
                <Field label="描述">
                  <textarea
                    rows={2}
                    value={action.description}
                    onChange={(e) =>
                      update(action.id, { description: e.target.value })
                    }
                  />
                </Field>
              </>
            ) : (
              <p>{action.description || "尚未填写描述"}</p>
            )}
            <div className="element-action-meta">
              <span>
                输入对象：
                {
                  draft.object_types.find((t) => t.id === action.input_type_id)
                    ?.name
                }
              </span>
              {!object && (
                <button
                  type="button"
                  className="element-text-button"
                  onClick={() =>
                    open({ kind: "action", id: action.id, tab: "actions" })
                  }
                >
                  查看所属对象
                  <ArrowRight size={14} />
                </button>
              )}
            </div>
            <div className="element-section-title">
              <h3>参数</h3>
              {canEdit && (
                <button
                  type="button"
                  className="element-text-button"
                  disabled={action.parameters.length >= 40}
                  onClick={() =>
                    update(action.id, {
                      parameters: [
                        ...action.parameters,
                        {
                          id: crypto.randomUUID(),
                          name: "",
                          technical_name: "",
                          value_kind: "string",
                          required: false,
                        },
                      ],
                    })
                  }
                >
                  <Plus size={14} />
                  新增参数
                </button>
              )}
            </div>
            {(action.parameters.length > 0 || canEdit) && (
              <div className="element-table-wrap">
                <table className="element-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>英文名称</th>
                      <th>类型</th>
                      <th>必填</th>
                      {canEdit && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {action.parameters.map((parameter, i) => (
                      <tr key={parameter.id}>
                        <td>
                          {canEdit ? (
                            <input
                              required
                              aria-label={`${prefix}参数名称 ${i + 1}`}
                              value={parameter.name}
                              onChange={(e) =>
                                changeParameter(parameter.id, {
                                  name: e.target.value,
                                })
                              }
                            />
                          ) : (
                            parameter.name
                          )}
                        </td>
                        <td>
                          {canEdit ? (
                            <input
                              required
                              pattern="[A-Za-z_][A-Za-z0-9_]*"
                              aria-label={`${prefix}参数英文名称 ${i + 1}`}
                              value={parameter.technical_name}
                              onChange={(e) =>
                                changeParameter(parameter.id, {
                                  technical_name: e.target.value,
                                })
                              }
                            />
                          ) : (
                            parameter.technical_name
                          )}
                        </td>
                        <td>
                          {canEdit ? (
                            <select
                              aria-label={`${prefix}参数类型 ${i + 1}`}
                              value={parameter.value_kind}
                              onChange={(e) =>
                                changeParameter(parameter.id, {
                                  value_kind: e.target.value,
                                })
                              }
                            >
                              {Object.entries(VALUE_KINDS).map(
                                ([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ),
                              )}
                            </select>
                          ) : (
                            VALUE_KINDS[parameter.value_kind]
                          )}
                        </td>
                        <td>
                          {canEdit ? (
                            <input
                              type="checkbox"
                              aria-label={`${prefix}参数必填 ${i + 1}`}
                              checked={parameter.required}
                              onChange={(e) =>
                                changeParameter(parameter.id, {
                                  required: e.target.checked,
                                })
                              }
                            />
                          ) : parameter.required ? (
                            "是"
                          ) : (
                            "否"
                          )}
                        </td>
                        {canEdit && (
                          <td>
                            <button
                              type="button"
                              className="icon-button"
                              aria-label={`删除参数 ${parameter.name || i + 1}`}
                              onClick={() =>
                                update(action.id, {
                                  parameters: action.parameters.filter(
                                    (p) => p.id !== parameter.id,
                                  ),
                                })
                              }
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!action.parameters.length && (
              <p className="element-note">暂无参数。</p>
            )}
            <h3>前置规则</h3>
            {canEdit
              ? availableRules.map((rule) => (
                  <label className="element-checkbox" key={rule.id}>
                    <input
                      type="checkbox"
                      checked={action.precondition_rule_ids.includes(rule.id)}
                      onChange={(e) =>
                        update(action.id, {
                          precondition_rule_ids: e.target.checked
                            ? [...action.precondition_rule_ids, rule.id]
                            : action.precondition_rule_ids.filter(
                                (id) => id !== rule.id,
                              ),
                        })
                      }
                    />
                    {rule.name}
                  </label>
                ))
              : action.precondition_rule_ids.map((id) => (
                  <p key={id}>
                    {draft.rules.find((r) => r.id === id)?.name ?? "规则不存在"}
                  </p>
                ))}
            {canEdit && (
              <button
                type="button"
                className="element-text-button"
                onClick={() =>
                  open({ kind: "object_type", id: type.id, tab: "rules" })
                }
              >
                管理规则
                <ArrowRight size={14} />
              </button>
            )}
            {!(canEdit
              ? availableRules.length
              : action.precondition_rule_ids.length) && (
              <p className="element-note">暂无前置规则。</p>
            )}
            <div className="element-section-title">
              <h3>效果</h3>
              {canEdit && (
                <button
                  type="button"
                  className="element-text-button"
                  disabled={action.effects.length >= 40}
                  onClick={() =>
                    update(action.id, {
                      effects: [
                        ...action.effects,
                        {
                          id: crypto.randomUUID(),
                          kind: "set_property",
                          property_id: properties[0]?.id ?? null,
                          link_type_id: null,
                          expression: "",
                        },
                      ],
                    })
                  }
                >
                  <Plus size={14} />
                  新增效果
                </button>
              )}
            </div>
            {action.effects.map((effect, i) =>
              canEdit ? (
                <div className="element-effect" key={effect.id}>
                  <div className="element-basic-grid">
                    <Field label="操作">
                      <select
                        aria-label={`${prefix}效果操作 ${i + 1}`}
                        value={effect.kind}
                        onChange={(e) => {
                          const kind = e.target.value as typeof effect.kind;
                          changeEffect(effect.id, {
                            kind,
                            property_id:
                              kind === "set_property"
                                ? (properties[0]?.id ?? null)
                                : null,
                            link_type_id:
                              kind === "set_property"
                                ? null
                                : (draft.link_types[0]?.id ?? null),
                          });
                        }}
                      >
                        {Object.entries(EFFECT_NAMES).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field
                      label={effect.kind === "set_property" ? "属性" : "关系"}
                    >
                      <select
                        required
                        aria-label={`${prefix}效果目标 ${i + 1}`}
                        value={
                          (effect.kind === "set_property"
                            ? effect.property_id
                            : effect.link_type_id) ?? ""
                        }
                        onChange={(e) =>
                          changeEffect(
                            effect.id,
                            effect.kind === "set_property"
                              ? { property_id: e.target.value }
                              : { link_type_id: e.target.value },
                          )
                        }
                      >
                        <option value="">请选择</option>
                        {(effect.kind === "set_property"
                          ? properties
                          : draft.link_types
                        ).map((target) => (
                          <option key={target.id} value={target.id}>
                            {target.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <Field label="表达式">
                    <textarea
                      maxLength={480}
                      rows={2}
                      value={effect.expression}
                      onChange={(e) =>
                        changeEffect(effect.id, { expression: e.target.value })
                      }
                    />
                  </Field>
                  <button
                    className="element-text-button"
                    type="button"
                    onClick={() =>
                      update(action.id, {
                        effects: action.effects.filter(
                          (e) => e.id !== effect.id,
                        ),
                      })
                    }
                  >
                    <Trash2 size={14} />
                    删除效果
                  </button>
                </div>
              ) : (
                <p key={effect.id}>
                  {EFFECT_NAMES[effect.kind]} ·{" "}
                  {draft.properties.find((p) => p.id === effect.property_id)
                    ?.name ??
                    draft.link_types.find((r) => r.id === effect.link_type_id)
                      ?.name}
                  <code>{effect.expression}</code>
                </p>
              ),
            )}
            {!action.effects.length && (
              <p className="element-note">暂无效果。</p>
            )}
            <EvidenceSection
              workspaceId={draft.workspace_id}
              evidence={action.evidence}
            />
          </article>
        );
      })}
      {!actions.length && <p className="element-empty">暂无动作。</p>}
    </section>
  );
}
