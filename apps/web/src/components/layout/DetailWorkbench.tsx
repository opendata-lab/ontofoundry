import { useContext, type ReactNode } from "react";
import { ContentBlock } from "./ContentBlock";
import { SeparateBlocks } from "./contentBlockContext";

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
  const separate = useContext(SeparateBlocks);
  return (
    <div className={`inspector-property-workbench${variant === "preview" ? " inspector-preview-workbench" : ""}${!detail ? " inspector-workbench-full" : ""}`}>
      <ContentBlock>{primary}</ContentBlock>
      {detail && <section className={`${separate ? "" : "inspector-property-detail"} flex min-w-0 flex-col gap-4`} aria-label={detailLabel}>
        {detail}
      </section>}
    </div>
  );
}
