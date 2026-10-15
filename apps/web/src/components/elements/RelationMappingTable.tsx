import { Search } from "lucide-react";
import { useState } from "react";
import {
  isObject,
  relationObjects,
  relationSource,
  relationTarget,
  type PanelProps,
} from "../../lib/elementModel";
import {
  branchDataset,
  objectMapping,
  shortObjectName,
  type MappedRelation,
} from "../../lib/objectMapping";
import { InspectorDialog } from "./InspectorDialog";
import { ReadonlyIcon } from "./MappingWidgets";
import { RelationCards } from "./RelationCards";
import {
  relationCreateReason,
  relationDeleteReason,
  relationEditReason,
  relationEndpoints,
} from "../../lib/relationEditing";

export function RelationMappingTable(props: PanelProps) {
  const { draft, type, nativeDraft, editing } = props;
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  if (!isObject(type)) return null;
  const record = objectMapping(draft, type, nativeDraft);
  const object = (id: string) => draft.object_types.find((o) => o.id === id);
  const relations = record.relations.filter((r) =>
    [
      r.definition.name,
      r.definition.technical_name,
      ...relationObjects(r.definition).map((id) => object(id)?.name),
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const selectedRelation = record.relations.find(
    (r) => r.definition.id === selected,
  );
  return (
    <>
      <div className="om-mapping-tools">
        <label className="om-search">
          <Search size={16} />
          <input
            aria-label="搜索关系"
            placeholder="搜索关系或关联对象"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="om-push om-inline">
          <button type="button" className="element-text-button" disabled>
            ＋ 添加关系
          </button>
          {editing && <ReadonlyIcon reason={relationCreateReason} />}
        </div>
      </div>
      <div className="om-table-wrap">
        <table className="om-table om-relations">
          <thead>
            <tr>
              <th>关系</th>
              <th>方向</th>
              <th>关联对象</th>
              <th>关联方式</th>
            </tr>
          </thead>
          <tbody>
            {relations.map((relation) => {
              const definition = relation.definition;
              const source = object(relationSource(definition));
              const targetId = relationTarget(definition);
              const related = relation.incoming ? source : object(targetId);
              const extras =
                definition.roles
                  ?.filter((r) => r.concept.kind === "object_type")
                  .slice(1) ?? [];
              const recordStyle =
                (definition.roles?.length ?? 1) > 1 ||
                definition.roles?.some((r) => r.concept.kind !== "object_type");
              const branch = relation.branches[0],
                table = branchDataset(branch);
              const ownerRecord = source
                ? objectMapping(draft, source, nativeDraft)
                : undefined;
              const mappingTable =
                !definition.data_join &&
                table &&
                (recordStyle || table.id !== ownerRecord?.mainDataset?.id);
              const join = definition.data_join;
              const target = object(targetId);
              const targetRecord = target
                ? objectMapping(draft, target, nativeDraft)
                : undefined;
              const condition = join
                ? (join.source_columns ?? [join.source_column])
                    .map(
                      (c, i) =>
                        `${c} = ${(join.target_columns ?? [join.target_column])[i] ?? ""}`,
                    )
                    .join(" · ")
                : branch?.roles[0]?.parts
                    .map((e, i) =>
                      targetRecord?.keys[i]?.expression
                        ? `${e.expression} = ${targetRecord.keys[i].expression}`
                        : "",
                    )
                    .filter(Boolean)
                    .join(" · ");
              return (
                <tr
                  key={definition.id}
                  className="om-open-row"
                  tabIndex={0}
                  aria-label={`查看${shortObjectName(definition)}`}
                  onClick={() => setSelected(definition.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(definition.id);
                    }
                  }}
                >
                  <td data-label="关系">
                    <div className="om-property-name">
                      {shortObjectName(definition)}
                      {relation.inherited && (
                        <span className="om-tag">继承</span>
                      )}
                    </div>
                    {recordStyle && (
                      <span className="om-record-label">记录型</span>
                    )}
                  </td>
                  <td data-label="方向">
                    <span className="muted">
                      {relation.incoming ? "← 入" : "→ 出"}
                    </span>
                  </td>
                  <td data-label="关联对象">
                    <div className="om-relation-object">
                      {related && <span>{shortObjectName(related)}</span>}
                      {extras.map((role) => {
                        const extra = object(role.concept.ref);
                        return (
                          extra && (
                            <small key={role.id}>
                              {shortObjectName(extra)}
                              {role.name && ` · ${role.name}`}
                            </small>
                          )
                        );
                      })}
                    </div>
                  </td>
                  <td data-label="关联方式">
                    {mappingTable ? (
                      <>
                        <span className="muted">映射表 </span>
                        <code title={table.source}>
                          {table.source.split(".").at(-1)}
                        </code>
                      </>
                    ) : condition ? (
                      <code>{condition}</code>
                    ) : (
                      <span className="muted">未绑定</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {!relations.length && (
              <tr>
                <td colSpan={4} className="om-blank">
                  无匹配关系
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {selectedRelation && (
        <RelationDialog
          key={selectedRelation.definition.id}
          {...props}
          relation={selectedRelation}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
function RelationDialog(
  props: PanelProps & { relation: MappedRelation; onClose: () => void },
) {
  const { relation, onClose } = props;
  const [editing, setEditing] = useState(props.editing);
  const [pending, setPending] = useState(props.draft);
  const [branchIndex, setBranchIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const local = { ...props, draft: pending, editing, change: setPending };
  const endpoints = relationEndpoints(local, relation.definition);
  const subtitle = [
    endpoints.source && shortObjectName(endpoints.source),
    endpoints.target && shortObjectName(endpoints.target),
  ]
    .filter(Boolean)
    .join(" → ");
  const reason = relationEditReason(local, relation);
  const redirect = () => {
    onClose();
    props.open(
      relation.inherited || relation.incoming
        ? {
            kind: "object_type",
            id: relation.inheritedFrom ?? endpoints.sourceId,
            tab: "relations",
            mode: "edit",
          }
        : {
            kind: "link_type",
            id: relation.definition.id,
            tab: "mapping",
            mode: "edit",
          },
    );
  };
  return (
    <InspectorDialog
      title={shortObjectName(relation.definition)}
      subtitle={subtitle}
      wide
      onClose={onClose}
      actions={
        !editing ? (
          props.canEdit !== false && (
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setEditing(true);
                props.requestEdit?.();
              }}
            >
              编辑
            </button>
          )
        ) : (
          <div className="om-inline">
            <button type="button" className="button button--secondary" disabled>
              删除
            </button>
            <ReadonlyIcon reason={relationDeleteReason} />
          </div>
        )
      }
      footer={
        editing && (
          <>
            <button
              type="button"
              className="button button--secondary om-push"
              disabled={busy}
              onClick={onClose}
            >
              取消
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={
                busy ||
                !!reason ||
                JSON.stringify(pending) === JSON.stringify(props.draft)
              }
              onClick={() => {
                setBusy(true);
                setError("");
                if (props.saveDraft)
                  void props
                    .saveDraft(pending)
                    .then((saved) => {
                      if (saved) onClose();
                      else setError("保存未完成，请关闭此窗口查看具体错误。");
                    })
                    .finally(() => setBusy(false));
                else {
                  props.change(pending);
                  onClose();
                }
              }}
            >
              保存
            </button>
          </>
        )
      }
    >
      <fieldset className="om-dialog-fields" disabled={busy}>
        <RelationCards
          {...local}
          relation={relation}
          branchIndex={branchIndex}
          onBranch={setBranchIndex}
        />
        {editing && reason && (
          <button
            type="button"
            className="element-text-button om-detail-section"
            onClick={redirect}
          >
            {relation.inherited
              ? "编辑父对象"
              : relation.incoming
                ? "编辑来源对象"
                : "编辑关系"}
          </button>
        )}
        {(props.saveError || error) && (
          <p role="alert" className="inline-error">
            {props.saveError || error}
          </p>
        )}
      </fieldset>
    </InspectorDialog>
  );
}
