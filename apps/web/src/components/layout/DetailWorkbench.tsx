import type { ReactNode } from "react";

/** A compact master list and a stable configuration pane within an inspector. */
export function DetailWorkbench({
  primary,
  detail,
  detailLabel,
  variant = "configuration",
}: {
  primary: ReactNode;
  detail?: ReactNode;
  detailLabel: string;
  variant?: "configuration" | "preview";
}) {
  return (
    <div className={`inspector-property-workbench${variant === "preview" ? " inspector-preview-workbench" : ""}${!detail ? " inspector-workbench-full" : ""}`}>
      <section className="flex min-w-0 flex-col gap-3">{primary}</section>
      {detail && <section className="inspector-property-detail flex min-w-0 flex-col gap-4" aria-label={detailLabel}>
        {detail}
      </section>}
    </div>
  );
}
