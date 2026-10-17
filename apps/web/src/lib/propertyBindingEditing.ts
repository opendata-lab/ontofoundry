import type { Draft, FieldBinding } from "../api/types";
import { effectiveProperties } from "./coreModel";

/** Session-local bindings survive temporary duplicate names without entering the model. */
export type PropertyBindingEdits = Map<string, Map<string, FieldBinding>>;

export function preservePropertyBindings(before: Draft, next: Draft, edits: PropertyBindingEdits): Draft {
  return {
    ...next,
    mappings: next.mappings.map((mapping) => {
      const previous = before.mappings.find((m) => m.id === mapping.id);
      if (!previous) return mapping;
      const oldProperties = effectiveProperties(before, mapping.type_id).map((p) => p.definition);
      const properties = effectiveProperties(next, mapping.type_id).map((p) => p.definition);
      const renamed = properties.some((p) => oldProperties.some((old) => old.id === p.id && old.technical_name !== p.technical_name));
      if (!renamed && mapping.fields === previous.fields) return mapping;
      const bindings = edits.get(mapping.id) ?? new Map(
        oldProperties.flatMap((p) => previous.fields[p.technical_name] ? [[p.id, previous.fields[p.technical_name]] as const] : []),
      );
      // Apply explicit binding changes in the previous namespace, only for unique names.
      for (const p of oldProperties) {
        const name = p.technical_name;
        if (oldProperties.filter((other) => other.technical_name === name).length !== 1) continue;
        if (mapping.fields[name] !== previous.fields[name]) {
          if (mapping.fields[name]) bindings.set(p.id, mapping.fields[name]);
          else bindings.delete(p.id);
        }
      }
      edits.set(mapping.id, bindings);
      const names = new Set(oldProperties.map((p) => p.technical_name));
      const fields = Object.fromEntries(Object.entries(mapping.fields).filter(([name]) => !names.has(name)));
      for (const p of properties) {
        const binding = bindings.get(p.id);
        if (!binding || properties.filter((other) => other.technical_name === p.technical_name).length !== 1) continue;
        if (binding.kind === "column" && !mapping.sources.some((source) => source.id === binding.source_id)) {
          bindings.delete(p.id);
          continue;
        }
        fields[p.technical_name] = binding;
      }
      return { ...mapping, fields };
    }),
  };
}
