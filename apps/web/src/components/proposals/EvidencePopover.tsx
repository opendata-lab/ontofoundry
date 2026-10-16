import { Collapse, Typography } from "antd";
import { FileText, UserCheck } from "lucide-react";
import type { EvidenceView } from "../../api/types";

const { Text } = Typography;

const lines = (start: number, end: number) => (start === end ? `第 ${start} 行` : `第 ${start}–${end} 行`);

/** Material quotes and manual confirmations behind a proposal. */
export function ReviewEvidence({ evidence }: { evidence: EvidenceView[] }) {
  if (!evidence.length) return <Text type="secondary">未附证据</Text>;
  return (
    <div className="flex flex-col gap-2">
      {evidence.map((entry) =>
        "material_id" in entry ? (
          <article key={entry.id} className="flex flex-col gap-1 rounded-sm bg-surface-soft px-3 py-2">
            <span className="inline-flex items-center gap-1 text-sm">
              <FileText size={14} />
              <strong>{entry.material_name || "材料"}</strong>
              <Text type="secondary">
                · {lines(entry.locator.line_start, entry.locator.line_end)}
                {entry.locator.heading ? ` · ${entry.locator.heading}` : ""}
                {entry.material_archived ? "（已归档）" : ""}
              </Text>
            </span>
            <blockquote className="m-0 border-l-2 border-rule-strong pl-3 text-sm whitespace-pre-wrap">
              {entry.quote || "未提供引用原文"}
            </blockquote>
            <Collapse
              ghost
              size="small"
              items={[
                {
                  key: "ids",
                  label: <Text type="secondary" className="text-xs">来源标识</Text>,
                  children: (
                    <dl className="m-0 grid grid-cols-[72px_1fr] gap-x-2 text-xs">
                      <dt className="text-muted">材料 ID</dt>
                      <dd className="m-0 break-all">{entry.material_id}</dd>
                      <dt className="text-muted">内容校验</dt>
                      <dd className="m-0 break-all">{entry.material_sha256}</dd>
                      <dt className="text-muted">证据 ID</dt>
                      <dd className="m-0 break-all">{entry.id}</dd>
                    </dl>
                  ),
                },
              ]}
            />
          </article>
        ) : (
          <article key={entry.id} className="flex flex-col gap-1 rounded-sm bg-surface-soft px-3 py-2">
            <span className="inline-flex items-center gap-1 text-sm">
              <UserCheck size={14} />
              <strong>人工确认</strong>
              <Text type="secondary">· {entry.created_by}</Text>
            </span>
            <span className="text-sm">{entry.note || "未提供说明"}</span>
          </article>
        ),
      )}
    </div>
  );
}
