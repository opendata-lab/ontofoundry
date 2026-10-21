import type { ReactNode } from "react";

/** Sources and fields share a row; instance previews keep the full width below. */
export function SourceFieldsLayout({ source, fields, children }: { source: ReactNode; fields: ReactNode; children?: ReactNode }) {
  return <div className="flex min-w-0 flex-col gap-4">
    <div className="source-fields-layout">{source}{fields}</div>
    {children}
  </div>;
}
