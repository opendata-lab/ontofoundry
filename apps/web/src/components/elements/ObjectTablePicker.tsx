import type { DataMapping, SemanticDataset } from "../../api/types";
import { isObject, type PanelProps } from "../../lib/elementModel";
import { objectMapping } from "../../lib/objectMapping";
import {
  selectMappingDataset,
  tableReplacementReason,
} from "../../lib/objectMappingEditing";
import { newId } from "../../lib/id";
import { DatasetPicker } from "../DatasetPicker";

/** Both overview and property rows select tables through the same object draft. */
export function ObjectTablePicker(
  props: PanelProps & {
    onClose: () => void;
    onDatasetSelected?: (dataset: SemanticDataset) => void;
    onLegacySelected?: (mapping: DataMapping) => void;
  },
) {
  if (!isObject(props.type)) return null;
  const { draft, nativeDraft, type, onClose } = props;
  const record = objectMapping(draft, type, nativeDraft);
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  const native = !!nativeDraft && (
    (record.mappings.length > 0 && !record.usesLegacyForm) ||
    !!draft._mapping_tables?.[type.id]
  );
  const model = record.models.find((m) =>
    m.concept_mappings?.some((cm) => cm.id === record.mappings[0]?.id),
  );
  const reason = tableReplacementReason(props);
  return (
    <DatasetPicker
      workspaceId={draft.workspace_id}
      open
      draft={draft}
      nativeDraft={nativeDraft}
      onOpenObject={(id) => props.open({ kind: "object_type", id, tab: "properties" })}
      datasets={nativeDraft && (!mapping || native)
        ? (model?.datasets ?? record.models.flatMap((m) => m.datasets)) : []}
      onSelectDataset={nativeDraft && (!mapping || native) ? (dataset) => {
        if (props.onDatasetSelected) props.onDatasetSelected(dataset);
        else selectMappingDataset(props, dataset);
        onClose();
      } : undefined}
      selectionReason={reason ?? undefined}
      onClose={onClose}
      onSelect={reason ? undefined : (connection, table) => {
        const selected: DataMapping = {
          id: mapping?.id ?? newId(),
          type_id: type.id,
          connection_alias: connection.name,
          schema_name: table.schema ?? null,
          table_name: table.name,
          key_column: "",
          fields: {},
        };
        if (props.onLegacySelected) props.onLegacySelected(selected);
        else props.change({
          ...draft,
          _mapping_tables: {},
          mappings: [...draft.mappings.filter((m) => m.type_id !== type.id), selected],
        });
        onClose();
      }}
    />
  );
}
