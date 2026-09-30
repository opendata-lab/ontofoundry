import { FileText, UserCheck } from "lucide-react";
import type { EvidenceView } from "../../api/types";

function lines(start: number, end: number) {
  return start === end ? `第 ${start} 行` : `第 ${start}–${end} 行`;
}

export function EvidenceLine({ evidence }: { evidence: EvidenceView }) {
  if (evidence.kind === "manual")
    return (
      <span className="evidence-line">
        <UserCheck size={13} aria-hidden />
        人工确认
      </span>
    );
  return (
    <span className="evidence-line">
      <FileText size={13} aria-hidden />
      证据：{evidence.material_name} {lines(evidence.locator.line_start, evidence.locator.line_end)}
    </span>
  );
}

export function EvidenceQuote({
  evidence,
  workspaceId,
}: {
  evidence: EvidenceView;
  workspaceId: string;
}) {
  if (evidence.kind === "manual")
    return (
      <blockquote className="evidence-quote">
        <p>{evidence.note || "（无说明）"}</p>
        <footer>
          人工确认 · {evidence.created_by} ·{" "}
          {new Date(evidence.created_at).toLocaleString("zh-CN", { hour12: false })}
        </footer>
      </blockquote>
    );
  const { line_start, line_end, heading } = evidence.locator;
  return (
    <blockquote className="evidence-quote">
      <p>{evidence.quote || "（未摘录原文）"}</p>
      <footer>
        {evidence.material_name}
        {heading ? ` · ${heading}` : ""} · {lines(line_start, line_end)}
        {evidence.material_archived && <span className="tag">已归档</span>}
        <a
          href={`/api/v1/workspaces/${workspaceId}/materials/${evidence.material_id}`}
          target="_blank"
          rel="noreferrer"
        >
          在材料中查看
        </a>
      </footer>
    </blockquote>
  );
}
