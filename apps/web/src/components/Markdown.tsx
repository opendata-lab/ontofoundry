import DOMPurify from "dompurify";
import { marked } from "marked";
import { useMemo } from "react";

marked.setOptions({ breaks: true, gfm: true });

export function Markdown({ children }: { children: string }) {
  const html = useMemo(() => {
    const rendered = marked.parse(String(children || ""), { async: false }) as string;
    return DOMPurify.sanitize(rendered, {
      USE_PROFILES: { html: true },
      FORBID_TAGS: ["style", "iframe", "object", "embed"],
    });
  }, [children]);
  return <div className="agent-markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}
