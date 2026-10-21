import { Alert, Button, Descriptions, Modal, Table, Typography } from "antd";
import { useState } from "react";
import type { Dataset, DuplicateCandidate, Draft, MaterialObject, ProposalItem } from "../../api/types";
import { byId, effectiveProperties } from "../../lib/coreModel";
import { SectionTitle, StatusMark } from "../layout";
import { ReviewEvidence } from "./EvidencePopover";
import { ProposalActions, ProposalStatusMark, type CardActions } from "./ProposalCard";
import { OPERATION, STATUS } from "./elementMeta";
import { FieldDiff } from "./FieldDiff";
import { useSourceIssues } from "./ProposalSourceIssues";
import { useConnectionNames } from "../../hooks/useConnectionNames";
import { acceptanceBlock, elementNames, mergedFact, requiredIds, reviewChanges, reviewKindName, valueText } from "./reviewMeta";

const { Text } = Typography;
const SIMILAR_MATCH: Record<string, string> = { name_in_query: "名称包含", query_in_name: "名称相近", description: "描述提到" };


function ReviseDialog({
  draft,
  item,
  candidate,
  busy,
  onCancel,
  onConfirm,
}: {
  draft: Draft;
  item: ProposalItem;
  candidate: DuplicateCandidate;
  busy: boolean;
  onCancel: () => void;
  onConfirm: (after: MaterialObject) => void;
}) {
  const existing = byId(draft.material_objects, candidate.id);
  const proposed = item.after as MaterialObject | null;
  const after = existing && proposed ? mergedFact(existing, proposed) : null;
  const properties = effectiveProperties(draft, candidate.type_id).map((p) => p.definition);
  return (
    <Modal
      open
      title={`改为更新已有实例：${candidate.display_text}`}
      onCancel={onCancel}
      okText="改为更新"
      cancelText="取消"
      okButtonProps={{ disabled: !after, loading: busy }}
      onOk={() => after && onConfirm(after)}
      width="var(--review-dialog-width)"
    >
      {!after ? (
        <Alert type="error" showIcon message="当前会话中找不到这个实例，请刷新后重试。" />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="m-0 text-xs text-muted">
            提案不再新建实例，而是更新已有实例：保留已有证据，追加本提案的证据；提案中有值的属性覆盖已有值。修订后会生成新的待审提案。
          </p>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={properties}
            columns={[
              { title: "属性", key: "name", render: (_, p) => (p.display_name || p.name) },
              { title: "已有值", key: "before", render: (_, p) => valueText(existing!.values[p.name]) },
              {
                title: "更新后",
                key: "after",
                render: (_, p) => {
                  const changed = existing!.values[p.name] !== after.values[p.name];
                  return <span className={changed ? "font-semibold text-success" : ""}>{valueText(after.values[p.name])}</span>;
                },
              },
            ]}
          />
          <Text type="secondary" className="text-xs">
            证据：已有 {existing!.evidence.length} 条，更新后 {after.evidence.length} 条
          </Text>
        </div>
      )}
    </Modal>
  );
}

export function ProposalDetail({
  item,
  items,
  draft,
  technical,
  busy,
  error,
  actions,
  onRevise,
  onReviseDataset,
  onReviseContent,
  workspaceId,
  onClose,
}: {
  item: ProposalItem;
  items: ProposalItem[];
  draft: Draft;
  technical: string;
  busy: boolean;
  error?: string;
  actions: CardActions;
  onRevise: (candidate: DuplicateCandidate, after: MaterialObject) => Promise<boolean>;
  onReviseDataset: (dataset: Dataset) => Promise<boolean>;
  onReviseContent: (fields: Record<string, unknown>) => Promise<boolean>;
  workspaceId: string;
  onClose: () => void;
}) {
  const [revising, setRevising] = useState<DuplicateCandidate | null>(null);
  const byIdMap = new Map(items.map((entry) => [entry.id, entry]));
  const deps = requiredIds(item);
  const changes = reviewChanges(item);
  const connectionNames = useConnectionNames(workspaceId);
  const source = useSourceIssues({ item, workspaceId, busy, fields: new Set(changes.map((c) => c.path)), onReviseDataset });
  // A declared rule the synced source column does not hold, beside that field (AR-03).
  const physicalMarks = Object.fromEntries((item.physical_differences ?? []).map((d) => [
    d.path,
    <StatusMark key={d.path} state="partial" label={`来源列 ${d.column} 允许为空`}
      title={`${d.connection_name} · ${[d.schema, d.table].filter(Boolean).join(".")}.${d.column}，同步于 ${d.observed_at ? new Date(d.observed_at).toLocaleString("zh-CN", { hour12: false }) : "未知时间"}；业务声明为必填，是否一致由审阅判断`} />,
  ]));
  const reason = item.reason.trim();
  const blocked = acceptanceBlock(item, byIdMap);
  const canRevise =
    item.status === "pending" && item.operation === "create" && item.target_kind === "material_object" && item.duplicate_candidates.length > 0;
  return (
    <Modal
      open
      onCancel={onClose}
      width="var(--review-detail-width)"
      title={
        <div className="flex flex-wrap items-center gap-2 pr-8">
          <span>
            {OPERATION[item.operation]}
            {reviewKindName(item.target_kind)} · {item.display_name}
          </span>
          <ProposalStatusMark status={item.status} />
          <code className="text-xs font-normal text-muted">{technical}</code>
        </div>
      }
      footer={
        <div className="flex items-center gap-3">
          <Text type="secondary" className="mr-auto text-left text-xs">
            {item.status === "accepted"
              ? "已接受。拒绝将撤销此项修改。"
              : item.status === "rejected"
                ? "恢复后回到待审；冲突项会保留原标记。"
                : blocked || "接受后将更新本体草稿。"}
          </Text>
          <ProposalActions item={item} busy={busy} blocked={blocked} actions={actions} size="middle" />
        </div>
      }
    >
      <div className="flex max-h-review-detail flex-col gap-4 overflow-auto">
        {["conflict", "stale"].includes(item.status) && (
          <Alert type="warning" showIcon message={`${STATUS[item.status]}：${item.status_reason || "当前目标已发生变化，请重新评估"}`} />
        )}
        {source.notes}
        {source.dialogs}
        {canRevise && (
          <section className="flex flex-col gap-2 border-b border-rule pb-4">
            <SectionTitle title="可能重复的已有实例" />
            <Text type="secondary" className="text-xs">
              确认是同一个实例时，把这条新建提案改为更新已有实例，不会自动合并。
            </Text>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={item.duplicate_candidates}
              columns={[
                { title: "已有实例", key: "display", render: (_, c) => c.display_text },
                { title: "类型", key: "type", render: (_, c) => (byId(draft.object_types, c.type_id)?.display_name || byId(draft.object_types, c.type_id)?.name) },
                {
                  title: "",
                  key: "action",
                  width: 120,
                  render: (_, c) => (
                    <Button size="small" disabled={busy} onClick={() => setRevising(c)}>
                      改为更新
                    </Button>
                  ),
                },
              ]}
            />
          </section>
        )}
        <section className="flex flex-col gap-2 border-b border-rule pb-4">
          <SectionTitle title="字段差异" note={`${changes.length} 处改动`} />
          <FieldDiff
            changes={changes}
            beforeLabel="修改前"
            names={new Map([...connectionNames, ...elementNames(draft, items)])}
            annotations={{ ...source.marks, ...physicalMarks }}
            editDisabled={busy}
            onEdit={
              item.status === "pending" && (item.operation === "create" || item.operation === "update") && item.after
                ? (path, value) => onReviseContent({ [path]: value })
                : undefined
            }
          />
        </section>
        {!!item.similar_definitions?.length && (
          <section className="flex flex-col gap-2 border-b border-rule pb-4">
            <SectionTitle title="可能已有的定义" note="供参考，确认重复时拒绝本提案并在对话中要求复用" />
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {item.similar_definitions.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2">
                  <span>{d.display_name || d.name}</span>
                  <code className="text-xs text-muted">{d.name}</code>
                  <Text type="secondary" className="text-xs">{SIMILAR_MATCH[d.match.by] ?? "名称相近"}「{d.match.text}」</Text>
                </li>
              ))}
            </ul>
          </section>
        )}
        {reason && (
          <section className="flex flex-col gap-1 border-b border-rule pb-4">
            <SectionTitle title="提案理由" />
            <p className="m-0 whitespace-pre-wrap">{reason}</p>
          </section>
        )}
        <section className="flex flex-col gap-2 border-b border-rule pb-4">
          <SectionTitle title="材料证据" note={`${item.evidence.length} 条引用`} />
          <ReviewEvidence evidence={item.evidence} />
        </section>
        <section className="flex flex-col gap-2 border-b border-rule pb-4">
          <SectionTitle title="依赖关系" note={deps.length > 0 ? `${deps.length} 项` : undefined} />
          {deps.length ? (
            <>
              <Descriptions
                size="small"
                column={1}
                items={deps.map((id) => {
                  const dependency = byIdMap.get(id);
                  return {
                    key: id,
                    label: dependency ? reviewKindName(dependency.target_kind) : "缺失",
                    children: dependency ? (
                      <span className="flex items-center gap-2">
                        <Button type="link" size="small" className="h-auto p-0" onClick={() => actions.open(dependency)}>
                          {dependency.display_name}
                        </Button>
                        <ProposalStatusMark status={dependency.status} />
                      </span>
                    ) : (
                      <Text type="danger">依赖提案缺失，暂不可接受</Text>
                    ),
                  };
                })}
              />
              <Text type="secondary" className="text-xs">
                接受时会一并接受尚待审核的依赖；撤销时会同步拒绝依赖此项的已接受提案。
              </Text>
            </>
          ) : (
            <Text type="secondary">本提案无依赖，可独立审核。</Text>
          )}
        </section>
        {error && <Alert type="error" showIcon message={error} />}
      </div>
      {revising && (
        <ReviseDialog
          draft={draft}
          item={item}
          candidate={revising}
          busy={busy}
          onCancel={() => setRevising(null)}
          onConfirm={(after) =>
            void onRevise(revising, after).then((ok) => {
              if (ok) {
                setRevising(null);
                onClose();
              }
            })
          }
        />
      )}
    </Modal>
  );
}
