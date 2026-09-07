export type Workspace = {
  id: string;
  slug: string;
  name: string;
  description: string;
  role: "admin" | "member" | null;
  visibility: "member" | "published_only";
  current_version: number | null;
  version_id: string | null;
  version_sha256: string | null;
  object_type_count: number;
  link_type_count: number;
  updated_at: string;
};

export type User = {
  id: string;
  subject: string;
  display_name: string;
  email: string | null;
};

export type AttributeDefinition = {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  value_kind: string;
  required: boolean;
  identifier: boolean;
};

export type ObjectType = {
  id: string;
  kind: "object_type";
  name: string;
  technical_name: string;
  description: string;
  tags: string[];
  attributes: AttributeDefinition[];
  attribute_count: number;
};

export type LinkType = {
  id: string;
  kind: "link_type";
  name: string;
  technical_name: string;
  description: string;
  tags: string[];
  source_type_id: string;
  target_type_id: string;
  multiplicity: string;
  attribute_count: 0;
  data_join?: { source_column: string; target_column: string } | null;
};

export type OntologyType = ObjectType | LinkType;

export type VersionSummary = {
  workspace_id: string;
  version_id: string;
  version: number;
  version_sha256: string;
  status: "published";
  message: string;
  published_at: string;
  validation: {
    standard: string;
    schema_status: "passed" | "failed";
    semantic_status: "passed" | "failed";
    errors: unknown[];
    warnings: unknown[];
    publishable: boolean;
  };
  counts: {
    object_types: number;
    link_types: number;
    attributes: number;
  };
};

export type GraphNode = {
  id: string;
  kind: "object_type" | "value_type";
  label: string;
  technical_name: string;
  description: string;
  tags: string[];
  attribute_count?: number;
  value_kind?: string;
  identifier?: boolean;
};

export type GraphEdge = {
  id: string;
  kind: "attribute" | "link_type";
  label: string;
  technical_name: string;
  source: string;
  target: string;
  multiplicity?: string;
  description?: string;
  tags?: string[];
};

export type TypeGraph = {
  workspace_id: string;
  version_id: string;
  version_sha256: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type WorkspaceOverview = {
  version: VersionSummary;
  graph: TypeGraph;
  details: {
    object_count: number;
    link_count: number;
    evidence_material_count: number;
    mapping_count: number;
    objects: { id: string; name: string; type_id: string }[];
    links: {
      id: string;
      type_id: string;
      source_id: string;
      target_id: string;
    }[];
    mappings: { id: string; type_id: string; table_name: string }[];
  } | null;
};

export type ObjectDefinition = Omit<ObjectType, "kind" | "attribute_count">;
export type LinkDefinition = Omit<LinkType, "kind" | "attribute_count">;
export type Evidence = {
  material_id: string;
  line_start: number;
  line_end: number;
  quote: string;
};
export type DocumentObject = {
  id: string;
  type_id: string;
  name: string;
  values: Record<string, string | number | boolean | null>;
  evidence: Evidence[];
};
export type DocumentLink = {
  id: string;
  type_id: string;
  source_id: string;
  target_id: string;
  evidence: Evidence[];
};
export type DataMapping = {
  id: string;
  type_id: string;
  connection_id: string;
  table_name: string;
  schema_name: string | null;
  key_column: string;
  fields: Record<string, string>;
};
export type Draft = {
  schema_version: string;
  workspace_id: string;
  object_types: ObjectDefinition[];
  link_types: LinkDefinition[];
  objects: DocumentObject[];
  links: DocumentLink[];
  mappings: DataMapping[];
};
export type Candidate = {
  id: string;
  status: string;
  reason: string;
  conflict?: string;
  evidence?: Evidence[];
} & (
  | { kind: "object_type"; value: ObjectDefinition }
  | { kind: "link_type"; value: LinkDefinition }
  | { kind: "object"; value: DocumentObject }
  | { kind: "link"; value: DocumentLink }
  | { kind: "clarification"; value: { name: string } }
);
export type ModelingSession = {
  id: string;
  title: string;
  workspace_id: string;
  base_version_id: string | null;
  revision: number;
  draft: Draft;
  graph: TypeGraph;
  candidates: Candidate[];
  messages: { role: string; content: string }[];
  material_ids: string[];
  task_status: string;
  task_detail: string;
  updated_at: string;
  validation?: VersionSummary["validation"];
};
export type OssieImportReport = {
  name: string;
  description: string;
  mode: "merge" | "replace";
  counts: {
    objects_added: number;
    objects_updated: number;
    links_added: number;
    links_updated: number;
    attributes_added: number;
    attributes_updated: number;
  };
  skipped: { path: string; reason: string }[];
  notes: string[];
};
export type OssieImportResult = ModelingSession & {
  import_report: OssieImportReport;
};
export type Material = {
  id: string;
  name: string;
  byte_size: number;
  chunk_count: number;
  sha256: string;
};
export type Capabilities = {
  agent_configured: boolean;
  model: string;
  max_file_mb: number;
  connections_configured: boolean;
  skills: string[];
};
export type DataConnection = {
  id: string;
  name: string;
  kind: string;
  host: string;
  port: number;
  database: string;
  username: string;
};
export type DataTable = {
  name: string;
  schema: string | null;
  columns: { name: string; type: string; primary_key: boolean }[];
};
