import type { ConceptRef } from "../api/types";
import type { ElementRequest } from "../lib/elementInspector";

/** An entity or value concept as a tag; opens its inspector when it can be opened. */
export function ConceptTag({
  label,
  kind,
  id,
  open,
}: {
  label: string;
  kind: ConceptRef["kind"];
  id?: string;
  open?: (request: ElementRequest) => void;
}) {
  if (open && id && (kind === "object_type" || kind === "value_type")) {
    return (
      <button
        type="button"
        className="tag tag--concept tag--link"
        title={`打开「${label}」`}
        onClick={() => open({ kind, id })}
      >
        {label}
      </button>
    );
  }
  return <span className="tag tag--concept">{label}</span>;
}
