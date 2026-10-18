import { Collapse, Descriptions, Typography } from "antd";
import { SectionTitle } from "../layout";
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
          <section key={entry.id} className="border-b border-rule-soft py-2">
            <div className="flex flex-col gap-1">
              <SectionTitle
                title={entry.material_name || "材料"}
                note={`${lines(entry.locator.line_start, entry.locator.line_end)}${entry.locator.heading ? ` · ${entry.locator.heading}` : ""}${entry.material_archived ? "（已归档）" : ""}`}
              />
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
                      <Descriptions
                        size="small"
                        column={1}
                        items={[
                          {
                            key: "material_id",
                            label: "材料 ID",
                            children: <span className="break-all text-xs">{entry.material_id}</span>,
                          },
                          {
                            key: "material_sha256",
                            label: "内容校验",
                            children: <span className="break-all text-xs">{entry.material_sha256}</span>,
                          },
                          {
                            key: "id",
                            label: "证据 ID",
                            children: <span className="break-all text-xs">{entry.id}</span>,
                          },
                        ]}
                      />
                    ),
                  },
                ]}
              />
            </div>
          </section>
        ) : (
          <section key={entry.id} className="border-b border-rule-soft py-2">
            <div className="flex flex-col gap-1">
              <SectionTitle title="人工确认" note={entry.created_by} />
              <span className="text-sm">{entry.note || "未提供说明"}</span>
            </div>
          </section>
        ),
      )}
    </div>
  );
}
