import original from "./nativeDraft.fixture.json";
import type {
  MappingNode,
  NativeDraft,
  SemanticDataset,
  SemanticField,
} from "../api/types";

/** Native authoring fixture with physical fields, cross-table references and record branches. */
export function nativeMappingFixture(): NativeDraft {
  const draft = structuredClone(original) as NativeDraft;
  draft.workspace_id = "w";
  const [supplier, product] = draft.object_types;
  supplier.name = "供应商";
  supplier.description = "供应商说明 别名：供方";
  supplier.identify_by = ["code"];
  product.name = "产品";
  draft.properties[0] = {
    ...draft.properties[0],
    name: "编码",
    identifier: true,
    required: true,
  };
  draft.properties.push({
    ...draft.properties[0],
    id: "name-property",
    name: "名称",
    technical_name: "name",
    identifier: false,
    required: false,
  });
  draft.link_types[0].name = "供应产品";
  draft.link_types[1].name = "调用记录";
  draft.link_types[1].roles = [
    draft.link_types[1].roles[0],
    {
      ...draft.link_types[1].roles[1],
      name: "次数",
      concept: { kind: "builtin", ref: "Integer" },
    },
  ];
  draft.link_types[1].verbalizes = [
    "{supplier} sells {product:product} {Integer:次数} times",
  ];
  draft.semantic_models = [
    { id: "model", name: "business", map_name: "warehouse" },
  ];
  const fields = (
    dataset_id: string,
    values: [string, string][],
  ): (SemanticField & { dataset_id: string })[] =>
    values.map(([name, expression]) => ({
      id: `${dataset_id}-${name}`,
      dataset_id,
      name,
      expression: { dialects: [{ dialect: "ANSI_SQL", expression }] },
    }));
  draft.datasets = [
    {
      id: "s",
      semantic_model_id: "model",
      name: "suppliers",
      source: "public.dim_supplier",
      primary_key: ["code"],
      unique_keys: [],
    },
    {
      id: "p",
      semantic_model_id: "model",
      name: "products",
      source: "public.dim_product",
      primary_key: ["id"],
      unique_keys: [],
    },
    {
      id: "events",
      semantic_model_id: "model",
      name: "events",
      source: "public.fact_calls",
      primary_key: [],
      unique_keys: [],
    },
  ] as (Omit<SemanticDataset, "fields"> & { semantic_model_id: string })[];
  draft.dataset_fields = [
    ...fields("s", [
      ["code", "supplier_code"],
      ["name", "name"],
      ["ref", "product_id"],
    ]),
    ...fields("p", [["id", "product_id"]]),
    ...fields("events", [
      ["owner", "supplier_code"],
      ["ref", "product_id"],
      ["name", "supplier_name"],
    ]),
  ];
  draft.concept_mappings = [
    {
      id: "cm-s",
      semantic_model_id: "model",
      concept_id: { kind: "object_type", ref: supplier.id },
    },
    {
      id: "cm-p",
      semantic_model_id: "model",
      concept_id: { kind: "object_type", ref: product.id },
    },
  ];
  const nodes: MappingNode[] = [];
  const node = (
    id: string,
    parent_id: string | null,
    kind: MappingNode["kind"],
    slot: MappingNode["slot"],
    values: Partial<MappingNode> = {},
    cm = "cm-s",
  ) =>
    nodes.push({
      id,
      parent_id,
      kind,
      slot,
      concept_mapping_id: cm,
      ...values,
    });
  node("key-s", null, "object", "object_mappings", {
    expression: "suppliers.code",
  });
  node(
    "key-p",
    null,
    "object",
    "object_mappings",
    { expression: "products.id" },
    "cm-p",
  );
  node("properties", null, "link", "link_mappings");
  node("property-owner", "properties", "object", "object_mapping", {
    expression: "suppliers.code",
  });
  node("code-link", "properties", "link", "children", { relationship: "code" });
  node("code-value", "code-link", "object", "object_mapping", {
    expression: "suppliers.code",
    concept: { kind: "builtin", ref: "String" },
  });
  node("simple-root", null, "link", "link_mappings");
  node("simple-owner", "simple-root", "object", "object_mapping", {
    expression: "suppliers.code",
  });
  node("simple-link", "simple-root", "link", "children", {
    relationship: draft.link_types[0].technical_name,
  });
  node("simple-value", "simple-link", "object", "object_mapping", {
    expression: "events.ref",
    concept: { kind: "object_type", ref: product.id },
  });
  for (const [i, dataset] of ["events", "suppliers"].entries()) {
    node(`record-${i}`, null, "link", "link_mappings");
    node(`record-owner-${i}`, `record-${i}`, "object", "object_mapping", {
      expression: dataset === "events" ? "events.owner" : "suppliers.code",
    });
    node(`record-product-${i}`, `record-${i}`, "link", "children");
    node(
      `record-product-value-${i}`,
      `record-product-${i}`,
      "object",
      "object_mapping",
      {
        expression: `${dataset}.ref`,
        concept: { kind: "object_type", ref: product.id },
      },
    );
    node(`record-count-${i}`, `record-product-${i}`, "link", "children", {
      relationship: draft.link_types[1].technical_name,
    });
    node(
      `record-count-value-${i}`,
      `record-count-${i}`,
      "object",
      "object_mapping",
      { expression: "10", concept: { kind: "builtin", ref: "Integer" } },
    );
  }
  draft.mapping_nodes = nodes;
  draft._legacy_form = {
    mappings: [],
    joins: {},
    mapping_status: {
      [supplier.id]: {
        state: "readonly",
        reason: "multiple_datasets",
        message: "复杂映射暂不支持实例查询（涉及多个数据集）",
        dataset_id: null,
      },
    },
  };
  return draft;
}
