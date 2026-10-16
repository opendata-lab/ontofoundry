import DOMPurify from "dompurify";
import { marked } from "marked";
import { useMemo } from "react";

marked.setOptions({ breaks: true, gfm: true });

const PROSE = [
  "whitespace-normal [&>:first-child]:mt-0 [&>:last-child]:mb-0",
  "[&_p]:mb-2.5 [&_ul]:mb-2.5 [&_ol]:mb-2.5 [&_blockquote]:mb-2.5 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-[22px] [&_ol]:pl-[22px]",
  "[&_h1]:mt-[18px] [&_h1]:mb-2 [&_h1]:text-[18px] [&_h2]:mt-[18px] [&_h2]:mb-2 [&_h2]:text-base [&_h3]:mt-[18px] [&_h3]:mb-2 [&_h3]:text-sm [&_h4]:text-sm",
  "[&_code]:rounded-xs [&_code]:bg-surface-soft [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs",
  "[&_pre]:my-2.5 [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:bg-[#172033] [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-[11px] [&_pre]:leading-relaxed [&_pre]:whitespace-pre-wrap [&_pre]:text-[#edf2f7] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit",
  "[&_table]:my-2.5 [&_table]:w-full [&_table]:text-xs [&_td]:border [&_td]:border-rule [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-rule [&_th]:px-2 [&_th]:py-1 [&_a]:text-accent",
].join(" ");

export function Markdown({ children }: { children: string }) {
  const html = useMemo(() => {
    const rendered = marked.parse(String(children || ""), { async: false }) as string;
    return DOMPurify.sanitize(rendered, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style", "iframe", "object", "embed"],
    });
  }, [children]);
  return <div className={PROSE} dangerouslySetInnerHTML={{ __html: html }} />;
}
