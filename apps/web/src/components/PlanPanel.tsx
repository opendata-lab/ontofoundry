import { Button, Tooltip, Typography } from "antd";
import { Check, Copy, Download, X } from "lucide-react";
import { useState } from "react";
import { copyText, downloadText } from "../lib/clipboard";
import { Panel } from "./layout";
import { Markdown } from "./Markdown";

export type OpenPlan = { title: string; body: string; markdown: string };

/** A plan expanded from the conversation's plan card, shown beside it. */
export function PlanPanel({ plan, onClose }: { plan: OpenPlan; onClose: () => void }) {
  const [copied, setCopied] = useState<"idle" | "done" | "failed">("idle");
  const copy = () =>
    copyText(plan.markdown)
      .then(() => setCopied("done"))
      .catch(() => setCopied("failed"));
  const fileName = `${plan.title.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "") || "plan"}.md`;
  return (
    <Panel fill className="min-w-0">
      <div className="flex items-start gap-2 border-b border-rule px-4 py-3" role="toolbar" aria-label="计划">
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
      {/* A wide concept table scrolls on its own; the column keeps its width. */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 text-sm leading-base text-ink [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_td]:min-w-20 [&_th]:min-w-20">
        <Markdown>{plan.body}</Markdown>
      </div>
    </Panel>
  );
}
