import { Alert, Button, Descriptions, Modal, Table, Typography } from "antd";
import { useState } from "react";
import type { DuplicateCandidate, Draft, MaterialObject, ProposalItem } from "../../api/types";
import { byId, effectiveProperties } from "../../lib/coreModel";
import { SectionTitle } from "../layout";
import { ReviewEvidence } from "./EvidencePopover";
import { ProposalActions, ProposalStatusMark, type CardActions } from "./ProposalCard";
import { OPERATION, STATUS } from "./elementMeta";
import { FieldDiff } from "./FieldDiff";
import { acceptanceBlock, elementNames, mergedFact, requiredIds, reviewChanges, reviewKindName, valueText } from "./reviewMeta";

const { Text } = Typography;


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
      title={`改为更新已有事实：${candidate.display_text}`}
      onCancel={onCancel}
      okText="改为更新"
      cancelText="取消"
      okButtonProps={{ disabled: !after, loading: busy }}
      onOk={() => after && onConfirm(after)}
      width="var(--review-dialog-width)"
    >
      {!after ? (
        <Alert type="error" showIcon message="当前会话中找不到这个事实，请刷新后重试。" />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="m-0 text-xs text-muted">
            提案不再新建事实，而是更新已有事实：保留已有证据，追加本提案的证据；提案中有值的属性覆盖已有值。修订后会生成新的待审提案。
          </p>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={properties}
            columns={[
              { title: "属性", key: "name", render: (_, p) => p.name },
              { title: "已有值", key: "before", render: (_, p) => valueText(existing!.values[p.technical_name]) },
              {
                title: "更新后",
                key: "after",
                render: (_, p) => {
                  const changed = existing!.values[p.technical_name] !== after.values[p.technical_name];
                  return <span className={changed ? "font-semibold text-success" : ""}>{valueText(after.values[p.technical_name])}</span>;
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
  onClose: () => void;
}) {
  const [revising, setRevising] = useState<DuplicateCandidate | null>(null);
  const byIdMap = new Map(items.map((entry) => [entry.id, entry]));
  const deps = requiredIds(item);
  const changes = reviewChanges(item);
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
        {canRevise && (
          <section className="flex flex-col gap-2 border-b border-rule pb-4">
            <SectionTitle title="可能重复的已有事实" />
            <Text type="secondary" className="text-xs">
              确认是同一个实例时，把这条新建提案改为更新已有事实，不会自动合并。
            </Text>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={item.duplicate_candidates}
              columns={[
                { title: "已有事实", key: "display", render: (_, c) => c.display_text },
                { title: "类型", key: "type", render: (_, c) => byId(draft.object_types, c.type_id)?.name },
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
          <FieldDiff changes={changes} beforeLabel="修改前" names={elementNames(draft, items)} />
        </section>
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
