import { X } from "lucide-react";
import type { EvidenceView } from "../../api/types";
import { ReviewPopover } from "./ReviewOverlays";
import { ReviewIcon } from "./ReviewIcon";

export function ReviewEvidence({ evidence }: { evidence: EvidenceView[] }) {
  if (!evidence.length) return <span className="muted">未附证据</span>;
  return <>{evidence.map((entry) => entry.kind === "manual" ? (
    <article className="evidence-item" key={entry.id}>
      <header><ReviewIcon name="evidence" /><strong>人工确认</strong><span>· {entry.created_by}</span></header>
      <blockquote>{entry.note || "未提供说明"}</blockquote>
    </article>
  ) : (
    <article className="evidence-item" key={entry.id}>
      <header><ReviewIcon name="evidence" /><strong>{entry.material_name || "材料"}</strong>
        <span>· {entry.locator?.line_start != null ? `第 ${entry.locator.line_start}${entry.locator.line_end && entry.locator.line_end !== entry.locator.line_start ? `–${entry.locator.line_end}` : ""} 行` : "未提供行号"}</span>
        {entry.material_archived && <span>（已归档）</span>}
      </header>
      <blockquote>{entry.quote || "未提供引用原文"}</blockquote>
      <details className="provenance"><summary>来源标识</summary><dl>
        <dt>材料 ID</dt><dd>{entry.material_id || "未提供"}</dd>
        <dt>内容校验</dt><dd>{entry.material_sha256 || "未提供"}</dd>
        <dt>证据 ID</dt><dd>{entry.id || "未提供"}</dd>
      </dl></details>
    </article>
  ))}</>;
}

export function EvidencePopover({ evidence, anchor, onClose }: {
  evidence: EvidenceView[];
  anchor: HTMLElement;
  onClose: () => void;
}) {
  return <ReviewPopover className="evidence-popover" anchor={anchor} label="材料证据" onClose={onClose}>
    <header className="popover-header"><h3>材料证据</h3>
      <button type="button" className="icon-btn" data-initial-focus aria-label="关闭证据" onClick={() => {
        onClose(); anchor.focus({ preventScroll: true });
      }}><X /></button>
    </header>
    <ReviewEvidence evidence={evidence} />
    <p className="popover-footer">来源和引用原文 · Esc 关闭</p>
  </ReviewPopover>;
}
