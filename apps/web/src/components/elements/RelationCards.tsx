import { isObject, type PanelProps } from "../../lib/elementModel";
import type { LinkTypeElement, NativeRole } from "../../api/types";
import {
  branchDataset,
  objectMapping,
  sourceColumns,
  shortObjectName,
  type MappingEntry,
  type MappedRelation,
} from "../../lib/objectMapping";
import { relationEntryChange } from "../../lib/objectMappingEditing";
import { FieldEditor, FieldValue, ReadonlyIcon } from "./MappingWidgets";

import {
  mappingTableReason,
  relationEditReason,
  relationEndpoints,
} from "../../lib/relationEditing";

/** Shared Fabric-style relationship form in both object and standalone relation popups. */
export function RelationCards(
  props: PanelProps & {
    relation: MappedRelation;
    branchIndex: number;
    onBranch: (index: number) => void;
  },
) {
  const {
    draft,
    nativeDraft,
    editing,
    change,
    relation,
    branchIndex,
    onBranch,
  } = props;
  const definition =
    draft.link_types.find((r) => r.id === relation.definition.id) ??
    relation.definition;
  const endpoints = relationEndpoints(props, definition);
  const { source, target } = endpoints;
  const sourceRecord = source
    ? objectMapping(draft, source, nativeDraft)
    : undefined;
  const targetRecord = target
    ? objectMapping(draft, target, nativeDraft)
    : undefined;
  const current =
    sourceRecord?.relations.find((r) => r.definition.id === definition.id) ??
    relation;
  const branch = current.branches[branchIndex];
  const dataset = branchDataset(branch);
  const mappingTable =
    !definition.data_join &&
    !!dataset &&
    (dataset.id !== sourceRecord?.mainDataset?.id ||
      (definition.roles?.length ?? 1) > 1);
  const reason = relationEditReason(props, relation);
  const canEdit = editing && !reason;
  const canEditDefinition = editing && !isObject(props.type);
  const updateDefinition = (patch: Partial<LinkTypeElement>) =>
    change({
      ...draft,
      link_types: draft.link_types.map((r) =>
        r.id === definition.id ? { ...r, ...patch } : r,
      ),
    });
  const roleReason = isObject(props.type)
    ? "角色定义不属于当前对象的保存范围，请打开关系单独编辑。"
    : current.branches.length
      ? "更改角色对象或类型需要同步更新原生映射树；请在「数据映射 › 语义模型 › 概念映射」中编辑。"
      : null;
  const roleTypes: Record<string, string> = {
    String: "文本",
    Integer: "整数",
    Decimal: "小数",
    Float: "小数",
    Boolean: "布尔",
    Date: "日期",
    DateTime: "日期时间",
  };
  const updateRole = (role: NativeRole, ref: string) => {
    const previous =
      draft.object_types.find((o) => o.id === role.concept.ref)
        ?.technical_name ?? role.concept.ref;
    const next =
      draft.object_types.find((o) => o.id === ref)?.technical_name ?? ref;
    const suffix = role.name ? ":" + role.name : "";
    updateDefinition({
      roles: definition.roles?.map((r) =>
        r.id === role.id ? { ...r, concept: { ...r.concept, ref } } : r,
      ),
      verbalizes: definition.verbalizes?.map((text) =>
        text.replaceAll(`{${previous}${suffix}}`, `{${next}${suffix}}`),
      ),
    });
  };
  const join = definition.data_join;
  const sourceFields: MappingEntry[] = join
    ? (join.source_columns ?? [join.source_column]).map((expression) => ({
        value: expression,
        expression,
        mode: "field",
        dataset: sourceRecord?.mainDataset,
      }))
    : mappingTable
      ? (branch?.source ?? [])
      : (branch?.roles.find((r) => r.kind === "object_type")?.parts ?? []);
  const targetFields: MappingEntry[] = join
    ? (join.target_columns ?? [join.target_column]).map((expression) => ({
        value: expression,
        expression,
        mode: "field",
        dataset: targetRecord?.mainDataset,
      }))
    : mappingTable
      ? (branch?.roles.find((r) => r.kind === "object_type")?.parts ?? [])
      : (targetRecord?.keys ?? []);
  const updateJoin = (
    index: number,
    expression: string,
    side: "source" | "target",
  ) => {
    const sources = sourceFields.map((e) => e.expression),
      targets = targetFields.map((e) => e.expression);
    if (!sources.length) sources.push("");
    if (!targets.length) targets.push("");
    (side === "source" ? sources : targets)[index] = expression;
    updateDefinition({
      data_join: {
        source_column: sources[0],
        target_column: targets[0],
        ...(sources.length > 1
          ? { source_columns: sources, target_columns: targets }
          : {}),
      },
    });
  };
  const propertyName = (record: typeof sourceRecord, index: number) =>
    record?.properties.filter((p) => p.property.identifier)[index]?.property
      .technical_name ?? record?.keys[index]?.label;
  const field = (
    entry: MappingEntry | undefined,
    label: string,
    index: number,
    side?: "source" | "target",
  ) => (
    <label className="om-relation-field">
      <span className="om-label">{label}</span>
      {canEdit && entry?.nodeId ? (
        <FieldEditor
          entry={entry}
          label={`${label} `}
          onChange={(next) => change(relationEntryChange(props, entry, next))}
        />
      ) : canEdit && side && (!nativeDraft || join) ? (
        <select
          aria-label={label}
          value={entry?.expression ?? ""}
          onChange={(e) => updateJoin(index, e.target.value, side)}
        >
          <option value="">未绑定</option>
          {[
            ...new Set([
              ...sourceColumns(
                side === "source"
                  ? sourceRecord?.mainDataset
                  : targetRecord?.mainDataset,
              ),
              ...(entry?.expression ? [entry.expression] : []),
            ]),
          ].map((column) => (
            <option key={column}>{column}</option>
          ))}
        </select>
      ) : entry ? (
        <FieldValue entry={entry} shorten main={entry.dataset} />
      ) : (
        <span className="muted">未绑定</span>
      )}
    </label>
  );
  const endpointCard = (side: "source" | "target") => {
    const object = side === "source" ? source : target;
    const record = side === "source" ? sourceRecord : targetRecord;
    const title = side === "source" ? "来源对象" : "目标对象";
    const objectReason = isObject(props.type)
      ? "关系端点不属于当前对象的保存范围，请打开关系单独编辑。"
      : nativeDraft && current.branches.length
        ? "当前关系已有原生角色映射，更换端点需要同步重建映射树；请在「数据映射 › 语义模型 › 概念映射」中编辑。"
        : null;
    const identifiers =
      record?.properties.filter((p) => p.property.identifier) ?? [];
    return (
      <section className="om-relationship-card">
        <h3>{title}</h3>
        <div className="om-relation-field">
          <span className="om-label">对象</span>
          {editing ? (
            <div className="om-inline">
              <select
                aria-label={title}
                disabled={!!objectReason}
                value={object?.id ?? ""}
                onChange={(e) => {
                  if (nativeDraft && definition.owner_ref) {
                    const ownerSide =
                      definition.endpoint_direction === "reverse"
                        ? "target"
                        : "source";
                    const nextObject = draft.object_types.find(
                      (o) => o.id === e.target.value,
                    );
                    const role = definition.roles?.find(
                      (r) => r.concept.kind === "object_type",
                    );
                    const roleName =
                      side === ownerSide
                        ? definition.owner_role_name
                        : role?.name;
                    const before = `{${object?.technical_name ?? ""}${roleName ? ":" + roleName : ""}}`;
                    const after = `{${nextObject?.technical_name ?? ""}${roleName ? ":" + roleName : ""}}`;
                    const verbalizes = definition.verbalizes?.map((text) =>
                      text.replaceAll(before, after),
                    );
                    if (side === ownerSide)
                      updateDefinition({
                        verbalizes,
                        owner_ref: {
                          ...definition.owner_ref,
                          ref: e.target.value,
                        },
                        [side === "source"
                          ? "source_type_id"
                          : "target_type_id"]: e.target.value,
                      });
                    else {
                      updateDefinition({
                        verbalizes,
                        roles: definition.roles?.map((r) =>
                          r.id === role?.id
                            ? {
                                ...r,
                                concept: { ...r.concept, ref: e.target.value },
                              }
                            : r,
                        ),
                        [side === "source"
                          ? "source_type_id"
                          : "target_type_id"]: e.target.value,
                      });
                    }
                  } else
                    updateDefinition({
                      [side === "source" ? "source_type_id" : "target_type_id"]:
                        e.target.value,
                      data_join: null,
                    });
                }}
              >
                <option value="">未绑定</option>
                {draft.object_types.map((o) => (
                  <option key={o.id} value={o.id}>
                    {shortObjectName(o)}
                  </option>
                ))}
              </select>
              <ReadonlyIcon reason={objectReason} />
            </div>
          ) : (
            object && <span>{shortObjectName(object)}</span>
          )}
        </div>
        <div className="om-relation-field">
          <span className="om-label">关联属性</span>
          {editing ? (
            <div className="om-inline">
              <select
                disabled
                aria-label={`${title}关联属性`}
                value={identifiers[0]?.property.id ?? ""}
              >
                <option value="">未绑定</option>
                {record?.properties.map((p) => (
                  <option key={p.property.id} value={p.property.id}>
                    {p.property.name} · {p.property.technical_name}
                  </option>
                ))}
              </select>
              <ReadonlyIcon reason="关联属性引用对象的实例标识；当前关系接口不能更改对象的实例标识，请打开对应对象设置。" />
            </div>
          ) : (
            identifiers.map((p) => (
              <span key={p.property.id}>
                {p.property.name} · {p.property.technical_name}
              </span>
            ))
          )}
        </div>
      </section>
    );
  };
  const primaryRole = branch?.roles.find((r) => r.kind === "object_type");
  const extraRoles =
    definition.roles
      ?.filter((r) => r.concept.kind === "object_type")
      .slice(1) ?? [];
  const attributes =
    definition.roles?.filter((r) => r.concept.kind !== "object_type") ?? [];
  return (
    <>
      {editing && (
        <div className="om-mapping-tools">
          <ReadonlyIcon reason={reason} />
          <div className="om-push om-inline">
            <button
              type="button"
              className="element-text-button"
              disabled={
                (!!nativeDraft &&
                  (current.branches.length > 0 ||
                    definition.roles?.length !== 1)) ||
                isObject(props.type) ||
                !source ||
                !target
              }
              onClick={() =>
                updateDefinition({
                  source_type_id: definition.target_type_id,
                  target_type_id: definition.source_type_id,
                  ...(join
                    ? {
                        data_join: {
                          source_column: join.target_column,
                          target_column: join.source_column,
                          source_columns: join.target_columns,
                          target_columns: join.source_columns,
                        },
                      }
                    : {}),
                })
              }
            >
              ⇄ 切换方向
            </button>
            {((nativeDraft &&
              (current.branches.length > 0 ||
                definition.roles?.length !== 1)) ||
              isObject(props.type)) && (
              <ReadonlyIcon reason="切换方向需要同步调整关系所属对象、角色与已有映射；请打开关系或在「数据映射 › 语义模型 › 概念映射」中编辑。" />
            )}
          </div>
        </div>
      )}
      <div className="om-relationship-cards">
        {endpointCard("source")}
        <span className="om-flow-arrow" aria-hidden="true">
          →
        </span>
        <section className="om-relationship-card om-relationship-card--middle">
          <h3>关系</h3>
          <label className="om-relation-field">
            <span className="om-label">名称</span>
            {canEditDefinition ? (
              <input
                aria-label="关系名称"
                required
                value={definition.name}
                onChange={(e) => updateDefinition({ name: e.target.value })}
              />
            ) : (
              <span>
                {shortObjectName(definition)}
                {editing && isObject(props.type) && (
                  <ReadonlyIcon reason="关系名称不属于当前对象的保存范围，请打开关系单独编辑。" />
                )}
              </span>
            )}
          </label>
          <div className="om-relation-field">
            <span className="om-label">使用映射表</span>
            {editing ? (
              <div className="om-inline">
                <input
                  type="checkbox"
                  role="switch"
                  checked={mappingTable}
                  disabled
                  aria-label="使用映射表"
                />
                <ReadonlyIcon reason={mappingTableReason} />
              </div>
            ) : (
              <span>{mappingTable ? "是" : "否"}</span>
            )}
          </div>
          {mappingTable && (
            <div className="om-relation-field">
              <span className="om-label">映射表</span>
              {current.branches.length > 1 ? (
                <select
                  aria-label="选择映射表"
                  value={branchIndex}
                  onChange={(e) => onBranch(Number(e.target.value))}
                >
                  {current.branches.map((b, i) => (
                    <option key={b.id} value={i}>
                      {branchDataset(b)?.source ?? "未绑定"}
                    </option>
                  ))}
                </select>
              ) : (
                <code title={dataset?.source}>
                  {dataset?.source.split(".").at(-1)}
                </code>
              )}
              {editing && <ReadonlyIcon reason={mappingTableReason} />}
            </div>
          )}
          <div className="om-mapping-fields">
            {Array.from(
              { length: Math.max(1, sourceFields.length, targetFields.length) },
              (_, i) => (
                <div key={i}>
                  {field(
                    sourceFields[i],
                    `来源 · ${source ? shortObjectName(source) : "来源对象"}${propertyName(sourceRecord, i) ? "." + propertyName(sourceRecord, i) : ""}`,
                    i,
                    "source",
                  )}
                  {field(
                    targetFields[i],
                    `目标 · ${target ? shortObjectName(target) : "目标对象"}${propertyName(targetRecord, i) ? "." + propertyName(targetRecord, i) : ""}`,
                    i,
                    "target",
                  )}
                </div>
              ),
            )}
          </div>
          {extraRoles.length > 0 && (
            <section className="om-extra-section">
              <h3>其他角色</h3>
              {extraRoles.map((role, i) => {
                const mapped = branch?.roles.filter(
                  (r) => r.kind === "object_type",
                )[i + 1];
                const object = draft.object_types.find(
                  (o) => o.id === role.concept.ref,
                );
                return (
                  <div key={role.id}>
                    <span className="om-label">{role.name}</span>
                    {editing ? (
                      <div className="om-inline">
                        <select
                          aria-label={`${role.name ?? "角色"}对象`}
                          value={role.concept.ref}
                          disabled={!!roleReason}
                          onChange={(e) => updateRole(role, e.target.value)}
                        >
                          {draft.object_types.map((o) => (
                            <option key={o.id} value={o.id}>
                              {shortObjectName(o)}
                            </option>
                          ))}
                        </select>
                        <ReadonlyIcon reason={roleReason} />
                      </div>
                    ) : (
                      object && <span>{shortObjectName(object)}</span>
                    )}
                    {(mapped?.parts ?? []).map((entry, index) => (
                      <div key={entry.nodeId ?? index}>
                        {field(
                          entry,
                          `${role.name ?? shortObjectName(object ?? { name: "对象" })}来源字段`,
                          index,
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </section>
          )}
          {attributes.length > 0 && (
            <section className="om-extra-section">
              <h3>附加属性</h3>
              {attributes.map((role) => {
                const mapped = branch?.roles.find(
                  (r) => r.kind !== "object_type" && r.name === role.name,
                );
                return (
                  <div key={role.id}>
                    <div className="om-inline">
                      <span>{role.name}</span>
                      {editing ? (
                        <>
                          <select
                            aria-label={`${role.name ?? "附加属性"}类型`}
                            value={role.concept.ref}
                            disabled={
                              !!roleReason || role.concept.kind !== "builtin"
                            }
                            onChange={(e) => updateRole(role, e.target.value)}
                          >
                            {Object.entries(roleTypes).map(([value, name]) => (
                              <option key={value} value={value}>
                                {name}
                              </option>
                            ))}
                            {role.concept.kind !== "builtin" && (
                              <option value={role.concept.ref}>
                                {
                                  draft.value_types?.find(
                                    (v) => v.id === role.concept.ref,
                                  )?.name
                                }
                              </option>
                            )}
                          </select>
                          <ReadonlyIcon
                            reason={
                              roleReason ??
                              (role.concept.kind !== "builtin"
                                ? "此属性引用已声明的值类型，请打开对应值类型编辑。"
                                : null)
                            }
                          />
                        </>
                      ) : (
                        <span className="muted">
                          {roleTypes[role.concept.ref] ??
                            draft.value_types?.find(
                              (v) => v.id === role.concept.ref,
                            )?.name}
                        </span>
                      )}
                    </div>
                    {mapped?.parts.map((entry, index) => (
                      <div key={entry.nodeId ?? index}>
                        {field(
                          entry,
                          `${role.name ?? "附加属性"}来源字段`,
                          index,
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </section>
          )}
          {!primaryRole &&
            !join &&
            branch?.source.map((entry, index) =>
              field(entry, "来源字段", index),
            )}
        </section>
        <span className="om-flow-arrow" aria-hidden="true">
          →
        </span>
        {endpointCard("target")}
      </div>
    </>
  );
}
