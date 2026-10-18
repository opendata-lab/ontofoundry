import DOMPurify from "dompurify";
import { marked } from "marked";
import { useMemo } from "react";

marked.setOptions({ breaks: true, gfm: true });

const PROSE = [
  "whitespace-normal [&>:first-child]:mt-0 [&>:last-child]:mb-0",
  "[&_p]:mb-3 [&_ul]:mb-3 [&_ol]:mb-3 [&_blockquote]:mb-3 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-6 [&_ol]:pl-6",
  "[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-base [&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-base [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:text-sm [&_h4]:text-sm",
  "[&_code]:rounded-xs [&_code]:bg-surface-soft [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs",
  "[&_pre]:my-3 [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:bg-ink [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-xs [&_pre]:leading-base [&_pre]:whitespace-pre-wrap [&_pre]:text-surface [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-inherit",
  "[&_table]:my-3 [&_table]:w-full [&_table]:text-xs [&_td]:border [&_td]:border-rule [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-rule [&_th]:px-2 [&_th]:py-1 [&_a]:text-accent",
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
