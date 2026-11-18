import { Button, Tooltip, Typography } from "antd";
import { Check, Copy, Download, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { copyText, downloadText } from "../lib/clipboard";
import { Panel } from "./layout";
import { Markdown } from "./Markdown";

export type OpenPlan = { title: string; body: string; markdown: string; requestId?: string };

/** A plan expanded from the conversation's plan card, shown beside it. */
export function PlanPanel({ plan, onClose }: { plan: OpenPlan; onClose: () => void }) {
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");
  const resetTimer = useRef<number | null>(null);
  // A copy can settle after the panel closed or was replaced by another plan.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    };
  }, []);
  const settle = (outcome: "done" | "failed") => {
    if (!mounted.current) return;
    setCopied(outcome);
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    resetTimer.current = window.setTimeout(() => setCopied("idle"), 1500);
  };
  const copy = () => {
    if (resetTimer.current !== null) window.clearTimeout(resetTimer.current);
    copyText(plan.markdown).then(() => settle("done"), () => settle("failed"));
  };
  const fileName = `${plan.title.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "") || "plan"}.md`;
  return (
    <Panel fill className="min-w-0">
      <div className="flex shrink-0 items-start gap-2 border-b border-rule px-4 py-3" role="toolbar" aria-label="计划">
        <Typography.Title level={5} className="m-0 min-w-0 flex-1 leading-base">{plan.title}</Typography.Title>
        <Tooltip title="下载 Markdown">
          <Button size="small" type="text" aria-label="下载计划" icon={<Download size={15} />} onClick={() => downloadText(fileName, plan.markdown)} />
        </Tooltip>
        <Tooltip title={copied === "done" ? "已复制" : copied === "failed" ? "复制失败，请手动选择" : "复制"}>
          <Button size="small" type="text" aria-label="复制计划" icon={copied === "done" ? <Check size={15} /> : <Copy size={15} />} onClick={copy} />
        </Tooltip>
        <Tooltip title="关闭">
          <Button size="small" type="text" aria-label="关闭计划" icon={<X size={15} />} onClick={onClose} />
        </Tooltip>
      </div>
      {/* A wide concept table scrolls on its own; long identifiers wrap so the column keeps its width. */}
      <div className="min-h-0 min-w-0 flex-1 select-text overflow-y-auto px-4 py-3 text-sm leading-base text-ink wrap-anywhere [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_td]:min-w-20 [&_th]:min-w-20">
        <Markdown>{plan.body}</Markdown>
      </div>
    </Panel>
  );
}
