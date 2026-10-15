import { useState } from "react";
import type { Evidence } from "../../api/types";
import { FileText } from "lucide-react";
import {
  changeType,
  isObject,
  rulesFor,
  relationsFor,
  type ElementType,
  type PanelProps,
} from "../../lib/elementModel";
import { objectMapping, shortObjectName } from "../../lib/objectMapping";
import { InspectorDialog } from "./InspectorDialog";
import { InfoButton, ReadonlyIcon } from "./MappingWidgets";
import { IdentifierBar } from "./IdentifierBar";
import { ObjectRelationGraph } from "./ObjectRelationGraph";
export { PropertyMappingTable as PropertiesPanel } from "./PropertyMappingTable";
export { RelationMappingTable as RelationsPanel } from "./RelationMappingTable";

export function EvidenceSection({
  workspaceId,
  evidence,
}: {
  workspaceId: string;
  evidence: Evidence[];
}) {
  if (!evidence.length) return null;
  return (
    <section className="element-section element-evidence">
      <h3>来源证据</h3>
      {evidence.map((ev) => (
        <div className="element-evidence-row" key={ev.id}>
          {ev.kind === "material" ? (
            <>
              <a
                href={`/api/v1/workspaces/${workspaceId}/materials/${encodeURIComponent(ev.material_id)}`}
                target="_blank"
                rel="noreferrer"
              >
                <FileText size={18} />
                <span>
                  查看来源材料 · {ev.locator.line_start}–{ev.locator.line_end}{" "}
                  行
                </span>
              </a>
              <blockquote>“{ev.quote}”</blockquote>
            </>
          ) : (
            <>
              <FileText size={18} />
              <span>{ev.note}</span>
            </>
          )}
        </div>
      ))}
    </section>
  );
}
export function BasicPanel(props: PanelProps) {
  const { type, draft, editing, open, nativeDraft } = props;
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const update = (patch: Partial<ElementType>) => changeType(props, patch);
  const object = isObject(type) && type.concept_kind !== "value_type";
  const record = object ? objectMapping(draft, type, nativeDraft) : null;
  const alias = type.description?.match(/别名：(.+?)[。.]?$/)?.[1];
  const description = (type.description ?? "").split("别名：")[0].trim();
  const aliases = [
    ...new Set(
      [
        ...(alias?.split(/[、，,]/) ?? []),
        ...(isObject(type) ? (type.concept_context?.synonyms ?? []) : []),
      ]
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  ];
  const context = isObject(type) ? type.concept_context?.instructions : null;
  return (
    <div className={record ? "om-overview" : "om-overview om-overview--simple"}>
      <div className="om-summary">
        <section>
          <div className="om-section-head">
            <h3>基本信息</h3>
            {type.evidence.length > 0 && (
              <InfoButton
                label="来源证据"
                onClick={() => setEvidenceOpen(true)}
              />
            )}
          </div>
          <dl className="om-info-grid">
            {(editing || type.name) && (
              <>
                <dt>名称</dt>
                <dd>
                  {editing ? (
                    <input
                      aria-label="名称"
                      required
                      maxLength={240}
                      value={type.name}
                      onChange={(e) => update({ name: e.target.value })}
                    />
                  ) : (
                    type.name
                  )}
                </dd>
              </>
            )}
            {(editing || type.technical_name) && (
              <>
                <dt>英文名</dt>
                <dd>
                  {editing ? (
                    <input
                      aria-label="英文名"
                      readOnly
                      required
                      pattern="[A-Za-z_][A-Za-z0-9_]*"
                      value={type.technical_name}
                      onChange={(e) =>
                        update({ technical_name: e.target.value })
                      }
                    />
                  ) : (
                    <code>{type.technical_name}</code>
                  )}
                </dd>
              </>
            )}
            {isObject(type) && type.extends.length > 0 && (
              <>
                <dt>继承自</dt>
                <dd>
                  {type.extends.map((id) => {
                    const parent = draft.object_types.find((t) => t.id === id);
                    return (
                      parent && (
                        <button
                          type="button"
                          key={id}
                          className="element-text-button"
                          onClick={() => open({ kind: "object_type", id })}
                        >
                          {shortObjectName(parent)}
                        </button>
                      )
                    );
                  })}
                </dd>
              </>
            )}
            {(editing || description) && (
              <>
                <dt>描述</dt>
                <dd>
                  {editing ? (
                    <textarea
                      aria-label="描述"
                      rows={3}
                      maxLength={4000}
                      value={description}
                      onChange={(e) =>
                        update({
                          description:
                            e.target.value + (alias ? ` 别名：${alias}` : ""),
                        })
                      }
                    />
                  ) : (
                    description
                  )}
                </dd>
              </>
            )}
            {aliases.length > 0 && (
              <>
                <dt>同义词</dt>
                <dd>
                  {editing && isObject(type) ? (
                    <textarea
                      aria-label="同义词"
                      rows={2}
                      value={
                        type.concept_context?.synonyms.length
                          ? type.concept_context.synonyms.join("\n")
                          : aliases.join("\n")
                      }
                      onChange={(e) =>
                        update({
                          concept_context: {
                            synonyms: e.target.value
                              .split("\n")
                              .filter(Boolean),
                            instructions: context ?? null,
                          },
                        })
                      }
                    />
                  ) : (
                    aliases.join("、")
                  )}
                </dd>
              </>
            )}
            {context?.trim() && (
              <>
                <dt>上下文说明</dt>
                <dd>
                  {editing && isObject(type) ? (
                    <textarea
                      aria-label="上下文说明"
                      rows={2}
                      value={context ?? ""}
                      onChange={(e) =>
                        update({
                          concept_context: {
                            synonyms: type.concept_context?.synonyms ?? [],
                            instructions: e.target.value,
                          },
                        })
                      }
                    />
                  ) : (
                    context
                  )}
                </dd>
              </>
            )}
          </dl>
        </section>
        {record && (
          <>
            <section>
              <div className="om-section-head">
                <h3>实例标识</h3>
              </div>
              <IdentifierBar {...props} heading={false} />
            </section>
            <section>
              <div className="om-section-head">
                <h3>数据来源</h3>
              </div>
              <div className="om-sources-summary">
                {record.tables.length ? (
                  record.tables.map((table) => (
                    <div key={table.id}>
                      <span
                        className={
                          table.id === record.mainDataset?.id
                            ? "om-tag om-tag-key"
                            : "om-tag"
                        }
                      >
                        {table.id === record.mainDataset?.id ? "主表" : "附表"}
                      </span>
                      <code title={table.source}>
                        {table.source.split(".").at(-1)}
                      </code>
                    </div>
                  ))
                ) : (
                  <span className="muted">未绑定</span>
                )}
              </div>
            </section>
          </>
        )}
      </div>
      {record && <ObjectRelationGraph {...props} />}
      {evidenceOpen && (
        <InspectorDialog
          title="来源证据"
          onClose={() => setEvidenceOpen(false)}
        >
          <EvidenceSection
            workspaceId={draft.workspace_id}
            evidence={type.evidence}
          />
        </InspectorDialog>
      )}
    </div>
  );
}
export function RulesPanel(props: PanelProps) {
  const { draft, type, editing, change, open } = props;
  const rules = rulesFor(draft, type);
  return (
    <div className="om-table-wrap">
      <table className="om-table om-rules">
        <thead>
          <tr>
            <th>作用于</th>
            <th>类型</th>
            <th>规则</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => {
            const property = draft.properties.find(
              (p) => p.id === rule.owner_id,
            );
            const relation = draft.link_types.find(
              (r) => r.id === rule.owner_id,
            );
            const inheritedRelation = isObject(type)
              ? relationsFor(draft, type).find(
                  (r) => r.definition.id === rule.owner_id,
                )
              : undefined;
            const inherited = property
              ? property.owner_type_id !== type.id
              : relation
                ? !!inheritedRelation?.inherited
                : rule.owner_kind === "object_type" &&
                  rule.owner_id !== type.id;
            const ownerId =
              property?.owner_type_id ??
              inheritedRelation?.inheritedFrom ??
              rule.owner_id;
            const label =
              property?.name ??
              relation?.name ??
              (rule.owner_kind === "action"
                ? draft.actions.find((a) => a.id === rule.owner_id)?.name
                : "对象");
            return (
              <tr key={rule.id} data-element-id={rule.id}>
                <td>
                  <div className="om-property-name">
                    {label}
                    {inherited && <span className="om-tag">继承</span>}
                    {editing && inherited && (
                      <>
                        <ReadonlyIcon reason="继承规则属于父对象，请编辑父对象。" />
                        <button
                          type="button"
                          className="element-text-button"
                          onClick={() =>
                            open({
                              kind: "object_type",
                              id: ownerId,
                              tab: "rules",
                              mode: "edit",
                            })
                          }
                        >
                          编辑父对象
                        </button>
                      </>
                    )}
                  </div>
                  {property && (
                    <span className="om-sub">{property.technical_name}</span>
                  )}
                </td>
                <td>
                  <span className="om-tag">
                    {rule.rule_kind === "derivation" ? "派生" : "约束"}
                  </span>
                </td>
                <td>
                  {editing && !inherited && !relation ? (
                    <textarea
                      aria-label={`${label}规则条件`}
                      className="om-rule-expression"
                      value={rule.expression}
                      onChange={(e) =>
                        change({
                          ...draft,
                          rules: draft.rules.map((r) =>
                            r.id === rule.id
                              ? { ...r, expression: e.target.value }
                              : r,
                          ),
                        })
                      }
                    />
                  ) : (
                    <code className="om-rule-expression">
                      {rule.expression}
                    </code>
                  )}
                  {rule.description.trim() && (
                    <div className="om-rule-description muted">
                      {rule.description}
                    </div>
                  )}
                  {editing && relation && !inherited && (
                    <ReadonlyIcon reason="关系规则不属于当前对象的保存范围，请在「本体构建」中编辑对应关系规则。" />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
