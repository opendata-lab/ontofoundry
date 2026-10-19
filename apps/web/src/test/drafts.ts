// The shared core-1 examples with every default filled in, as the server
// returns a stored draft. Tests read real example graphs instead of
// hand-written fragments.
import type { CoreDraft } from "../api/core.generated";
import type { Draft, Metric } from "../api/types";
import { core1Example } from "./core1Fixtures";

export function storedDraft(source: CoreDraft): Draft {
  return {
    schema_version: "core-1",
    workspace_id: source.workspace_id,
    object_types: (source.object_types ?? []).map((o) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      extends: null,
      derived_by: [],
      title_property_id: null,
      ...o,
    })),
    properties: (source.properties ?? []).map((p) => ({
      description: "",
      synonyms: [],
      evidence: [],
      identifier: false,
      unique: false,
      required: false,
      ...p,
    })),
    link_types: (source.link_types ?? []).map((l) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      verbalizes: [],
      source_role_name: null,
      target_role_name: null,
      data_join: null,
      ...l,
    })),
    rules: (source.rules ?? []).map((r) => ({ description: "", evidence: [], ...r })),
    metrics: (source.metrics ?? []).map((m) => {
      const common = { description: "", synonyms: [], evidence: [] };
      if (m.kind === "simple") return { ...common, filters: [], measure: null, time_field: null, ...m } as Metric;
      if (m.kind === "expression") return { ...common, value_kind: null, time_field: null, ...m } as Metric;
      return { ...common, ...m } as Metric;
    }),
    datasets: (source.datasets ?? []).map((d) => ({
      description: "",
      dialect: null,
      schema_name: null,
      snapshot_date_column: null,
      columns: null,
      ...d,
    })),
    mappings: (source.mappings ?? []).map((m) => ({
      fields: {},
      membership_source_id: null,
      inherited_link_bindings: {},
      ...m,
      sources: (m.sources ?? []).map((s) => ({ key_columns: [], ...s })),
    })),
    material_objects: (source.material_objects ?? []).map((o) => ({ values: {}, evidence: [], ...o })),
    material_links: (source.material_links ?? []).map((l) => ({ evidence: [], ...l })),
  };
}

export const example = (name: string) => storedDraft(core1Example(name));
