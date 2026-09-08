import {
  ArrowLeft,
  Box,
  MessageSquareText,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { Draft, ObjectDefinition, LinkDefinition } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useModeling } from "../hooks/useModeling";
import { MappingForm } from "../components/MappingForm";
import { VerbalizationEditor } from "../components/VerbalizationEditor";
import { placeholders, valueConcept } from "../lib/verbalization";
import { usePageTab } from "../hooks/usePageTab";

// A reading the writer left blank is not a reading; keeping it would fail the
// model's non-empty rule at save time.
function clearBlankReadings<T extends ObjectDefinition | LinkDefinition>(
  type: T,
): T {
  const clean = (lines: string[] | undefined) =>
    (lines ?? []).map((line) => line.trim()).filter(Boolean);
  if ("attributes" in type)
    return {
      ...type,
      attributes: type.attributes.map((item) => ({
        ...item,
        verbalizes: clean(item.verbalizes),
      })),
    };
  return { ...type, verbalizes: clean(type.verbalizes) };
}

export function ObjectEditorPage({ relation = false }: { relation?: boolean }) {
  const { workspace } = useWorkspaceContext();
  const { typeId } = useParams();
  const navigate = useNavigate();
  const initialized = useRef("");
  const model = useModeling(workspace.id);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [type, setType] = useState<ObjectDefinition | LinkDefinition | null>(
    null,
  );
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reading, setReading] = useState("");
  const [dirty, setDirty] = useState(false);
  const [issues, setIssues] = useState<string[]>([]);
  usePageTab({
    title: type?.name ? `编辑 · ${type.name}` : undefined,
    dirty,
    busy,
  });
  useEffect(() => {
    if (!model.session) return;
    const key = `${model.session.id}/${relation}/${typeId}`;
    if (initialized.current === key) return;
    initialized.current = key;
    const d = structuredClone(model.session.draft);
    setDraft(d);
    const existing = (relation ? d.link_types : d.object_types).find(
      (t) => t.id === typeId,
    );
    if (existing) setType(existing);
    else if (typeId === "new")
      setType(
        relation
          ? {
              id: crypto.randomUUID(),
              name: "",
              technical_name: "",
              description: "",
              tags: [],
              source_type_id: d.object_types[0]?.id ?? "",
              target_type_id: d.object_types[1]?.id ?? "",
              multiplicity: "many_to_many",
            }
          : {
              id: crypto.randomUUID(),
              name: "",
              technical_name: "",
              description: "",
              tags: [],
              attributes: [],
            },
      );
  }, [model.session, typeId, relation]);
  const change = (value: Partial<ObjectDefinition & LinkDefinition>) => {
    setType((t) => (t ? { ...t, ...value } : t));
    setDirty(true);
    setSaved(false);
  };
  if (!model.session || !draft || !type)
    return (
      <div className="empty-state">{model.error || "正在打开编辑草稿…"}</div>
    );
  const steps = relation
    ? ["基本信息", "关系定义", "关系映射"]
    : ["基本信息", "数据映射", "属性定义", "属性映射", "关联关系"];
  const save = async () => {
    setBusy(true);
    model.setError("");
    setIssues([]);
    const next = structuredClone(draft);
    const trimmed = clearBlankReadings(type);
    if ("attributes" in trimmed)
      next.object_types = [
        ...next.object_types.filter((t) => t.id !== trimmed.id),
        trimmed,
      ];
    else
      next.link_types = [
        ...next.link_types.filter((t) => t.id !== trimmed.id),
        trimmed,
      ];
    try {
      const result = await modelingApi.save(model.session!, next);
      model.setSession(result);
      setDraft(result.draft);
      setSaved(true);
      setDirty(false);
      if (typeId === "new") {
        initialized.current = `${result.id}/${relation}/${type.id}`;
        navigate(
          `/workspaces/${workspace.id}/${relation ? "relations" : "objects"}/${type.id}/edit?session=${result.id}`,
          { replace: true },
        );
      }
      setIssues(
        (result.validation?.errors ?? []).map(
          (e) => (e as { message: string }).message,
        ),
      );
    } catch (e) {
      model.setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  return (
    <div className="ref-editor">
      <header className="breadcrumb-bar">
        <Link
          to={
            "../" +
            (relation ? "relations" : "objects") +
            "?session=" +
            model.session.id
          }
        >
          <ArrowLeft size={14} />
          {relation ? "本体关系" : "业务对象"}
        </Link>
        <span>/</span>
        <span>编辑本体 {type.name && "【" + type.name + "】"}</span>
        <div className="toolbar-spacer" />
        <Link to={"../builder?session=" + model.session.id}>返回建模会话</Link>
      </header>
      <div className="editor-steps">
        {steps.map((name, i) => (
          <button
            key={name}
            aria-current={i === step ? "step" : undefined}
            onClick={() => setStep(i)}
          >
            <b>{i + 1}</b>
            {name}
          </button>
        ))}
      </div>
      <div className="editor-scroll">
        <form
          className={
            "editor-form " +
            (step === 2 || step === 3 ? "editor-form--wide" : "")
          }
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          {step === 0 && (
            <>
              <h2>基本信息</h2>
              <label className="section-field">
                <span>
                  <em>*</em> 图标 & 名称
                </span>
                <div className="name-with-icon">
                  <span className="catalog-object-icon">
                    <Box size={22} />
                  </span>
                  <input
                    required
                    maxLength={240}
                    aria-label="本体名称"
                    value={type.name}
                    onChange={(e) => change({ name: e.target.value })}
                  />
                </div>
              </label>
              <label className="section-field">
                <span>
                  <em>*</em> API 标识
                </span>
                <input
                  required
                  pattern="[A-Za-z_][A-Za-z0-9_]*"
                  aria-label="API 标识"
                  value={type.technical_name}
                  onChange={(e) => change({ technical_name: e.target.value })}
                />
              </label>
              <label className="section-field">
                <span>标签</span>
                <input
                  aria-label="标签"
                  placeholder="使用逗号分隔标签"
                  value={type.tags.join(", ")}
                  onChange={(e) =>
                    change({
                      tags: e.target.value
                        .split(/[,，]/)
                        .map((t) => t.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </label>
              <label className="section-field">
                <span>描述</span>
                <textarea
                  rows={4}
                  value={type.description}
                  onChange={(e) => change({ description: e.target.value })}
                  maxLength={4000}
                />
              </label>
            </>
          )}
          {relation && step === 1 && "source_type_id" in type && (
            <>
              <h2>关系定义</h2>
              {(["source_type_id", "target_type_id"] as const).map((key, i) => (
                <label className="section-field" key={key}>
                  <span>{i ? "目标对象" : "源对象"}</span>
                  <select
                    value={type[key]}
                    onChange={(e) => change({ [key]: e.target.value })}
                  >
                    <option value="">请选择对象</option>
                    {draft.object_types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <label className="section-field">
                <span>关系基数</span>
                <select
                  value={type.multiplicity}
                  onChange={(e) => change({ multiplicity: e.target.value })}
                >
                  <option value="many_to_many">多对多</option>
                  <option value="many_to_one">多对一</option>
                  <option value="one_to_many">一对多</option>
                  <option value="one_to_one">一对一</option>
                </select>
              </label>
              <VerbalizationEditor
                label="自然语言读法"
                concepts={placeholders([
                  draft.object_types.find((t) => t.id === type.source_type_id)
                    ?.technical_name,
                  draft.object_types.find((t) => t.id === type.target_type_id)
                    ?.technical_name,
                ])}
                value={type.verbalizes}
                onChange={(verbalizes) => change({ verbalizes })}
              />
            </>
          )}
          {relation && step === 2 && "source_type_id" in type && (
            <>
              <h2>关系映射</h2>
              <p className="muted">
                在两个对象的数据表之间，按字段相等查找已有关系。跨连接不执行联邦查询。
              </p>
              <label className="show-attributes">
                <input
                  type="checkbox"
                  checked={!!type.data_join}
                  onChange={(e) =>
                    change({
                      data_join: e.target.checked
                        ? { source_column: "", target_column: "" }
                        : null,
                    })
                  }
                />
                配置字段关联
              </label>
              {type.data_join &&
                (["source", "target"] as const).map((side) => {
                  const endpoint = type[`${side}_type_id`];
                  const mapped = draft.mappings.find(
                    (m) => m.type_id === endpoint,
                  );
                  const key = `${side}_column` as const;
                  return (
                    <label key={side} className="section-field">
                      <span>
                        {side === "source" ? "源" : "目标"}字段 ·{" "}
                        {mapped?.table_name ?? "请先配置对象映射"}
                      </span>
                      <input
                        list={`join-columns-${side}`}
                        placeholder="选择或输入源表中的字段名"
                        value={type.data_join![key]}
                        onChange={(e) =>
                          change({
                            data_join: {
                              ...type.data_join!,
                              [key]: e.target.value,
                            },
                          })
                        }
                      />
                      <datalist id={`join-columns-${side}`}>
                        {[
                          ...new Set(
                            mapped
                              ? [
                                  mapped.key_column,
                                  ...Object.values(mapped.fields),
                                ]
                              : [],
                          ),
                        ].map((name) => (
                          <option key={name}>{name}</option>
                        ))}
                      </datalist>
                    </label>
                  );
                })}
            </>
          )}
          {!relation &&
            "attributes" in type &&
            (step === 1 || step === 3) &&
            type.reified_from && (
              <p className="muted">
                这是从 Apache Ossie 的 {type.reified_from.roles.length + 1}{" "}
                元关系拆出的事实对象，发布时写回原来的关系而不是一个独立概念，
                因此暂不支持配置数据映射。
              </p>
            )}
          {!relation &&
            "attributes" in type &&
            (step === 1 || step === 3) &&
            !type.reified_from && (
              <MappingForm
                workspaceId={workspace.id}
                type={type}
                mapping={mapping}
                fieldsOnly={step === 3}
                onChange={(m) => {
                  setDirty(true);
                  setDraft({
                    ...draft,
                    mappings: [
                      ...draft.mappings.filter((x) => x.type_id !== type.id),
                      m,
                    ],
                  });
                  setSaved(false);
                }}
              />
            )}
          {!relation && step === 2 && "attributes" in type && (
            <>
              <div className="mapping-heading">
                <h2>属性定义</h2>
                <button
                  className="button button--text"
                  type="button"
                  onClick={() =>
                    change({
                      attributes: [
                        ...type.attributes,
                        {
                          id: crypto.randomUUID(),
                          name: "",
                          technical_name: "",
                          description: "",
                          value_kind: "string",
                          required: false,
                          identifier: false,
                        },
                      ],
                    })
                  }
                >
                  <Plus size={14} />
                  新增属性
                </button>
              </div>
              <table className="ref-table attribute-editor">
                <thead>
                  <tr>
                    <th>属性名称</th>
                    <th>API 标识</th>
                    <th>数据类型</th>
                    <th>标识</th>
                    <th>必填</th>
                    <th>读法</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {type.attributes.flatMap((a, i) => [
                    <tr key={a.id}>
                      <td>
                        <input
                          aria-label={"属性名称 " + (i + 1)}
                          value={a.name}
                          onChange={(e) =>
                            change({
                              attributes: type.attributes.map((x) =>
                                x.id === a.id
                                  ? { ...x, name: e.target.value }
                                  : x,
                              ),
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={"属性标识 " + (i + 1)}
                          value={a.technical_name}
                          onChange={(e) =>
                            change({
                              attributes: type.attributes.map((x) =>
                                x.id === a.id
                                  ? { ...x, technical_name: e.target.value }
                                  : x,
                              ),
                            })
                          }
                        />
                      </td>
                      <td>
                        <select
                          value={a.value_kind}
                          aria-label={"属性类型 " + (i + 1)}
                          onChange={(e) =>
                            change({
                              attributes: type.attributes.map((x) =>
                                x.id === a.id
                                  ? { ...x, value_kind: e.target.value }
                                  : x,
                              ),
                            })
                          }
                        >
                          {[
                            "string",
                            "integer",
                            "decimal",
                            "float",
                            "boolean",
                            "date",
                            "datetime",
                          ].map((k) => (
                            <option key={k}>{k}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={"标识属性 " + (i + 1)}
                          checked={a.identifier}
                          onChange={(e) =>
                            change({
                              attributes: type.attributes.map((x) =>
                                x.id === a.id
                                  ? { ...x, identifier: e.target.checked }
                                  : x,
                              ),
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={"必填属性 " + (i + 1)}
                          checked={a.required}
                          onChange={(e) =>
                            change({
                              attributes: type.attributes.map((x) =>
                                x.id === a.id
                                  ? { ...x, required: e.target.checked }
                                  : x,
                              ),
                            })
                          }
                        />
                      </td>
                      <td>
                        <button
                          className="button button--text"
                          type="button"
                          aria-expanded={reading === a.id}
                          onClick={() =>
                            setReading(reading === a.id ? "" : a.id)
                          }
                        >
                          <MessageSquareText size={13} />
                          {a.verbalizes?.length ? "已自定义" : "默认"}
                        </button>
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          type="button"
                          aria-label={"删除属性 " + (i + 1)}
                          onClick={() =>
                            change({
                              attributes: type.attributes.filter(
                                (x) => x.id !== a.id,
                              ),
                            })
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>,
                    reading === a.id ? (
                      <tr key={a.id + ":reading"} className="attribute-reading">
                        <td colSpan={7}>
                          <VerbalizationEditor
                            label={
                              "「" + (a.name || a.technical_name) + "」读法"
                            }
                            concepts={placeholders([
                              type.technical_name,
                              valueConcept(type.technical_name, a),
                            ])}
                            value={a.verbalizes}
                            onChange={(verbalizes) =>
                              change({
                                attributes: type.attributes.map((x) =>
                                  x.id === a.id ? { ...x, verbalizes } : x,
                                ),
                              })
                            }
                          />
                        </td>
                      </tr>
                    ) : null,
                  ])}
                </tbody>
              </table>
              {!type.attributes.length && (
                <p className="muted">点击新增属性，定义本体的数据结构。</p>
              )}
            </>
          )}
          {!relation && step === 4 && (
            <>
              <h2>关联关系</h2>
              {draft.link_types
                .filter(
                  (r) =>
                    r.source_type_id === type.id ||
                    r.target_type_id === type.id,
                )
                .map((r) => (
                  <Link
                    key={r.id}
                    className="relation-list-row"
                    to={
                      "../relations/" +
                      r.id +
                      "/edit?session=" +
                      model.session!.id
                    }
                  >
                    {r.name}
                    <span>{r.technical_name}</span>
                  </Link>
                ))}
              <Link
                to={"../relations/new/edit?session=" + model.session.id}
                className="button button--text"
              >
                <Plus size={14} />
                新增关系
              </Link>
            </>
          )}
          <button type="submit" hidden />
        </form>
      </div>
      {(model.error || issues.length > 0) && (
        <div className="inline-error" role="alert">
          {model.error || issues.join("\n")}
        </div>
      )}
      <footer className="editor-footer">
        <span className="muted">
          {saved
            ? issues.length
              ? "草稿已保存，请修正校验问题后发布"
              : "草稿已保存"
            : "修改保存在会话草稿中"}
        </span>
        <div className="toolbar-spacer" />
        {step > 0 && (
          <button
            className="button button--secondary"
            onClick={() => setStep(step - 1)}
          >
            上一步
          </button>
        )}
        {step < steps.length - 1 && (
          <button
            className="button button--secondary"
            onClick={() => setStep(step + 1)}
          >
            下一步
          </button>
        )}
        <button
          className="button button--primary"
          onClick={save}
          disabled={busy || !type.name.trim() || !type.technical_name.trim()}
        >
          <Save size={14} />
          {busy ? "保存中…" : "保存草稿"}
        </button>
      </footer>
    </div>
  );
}
