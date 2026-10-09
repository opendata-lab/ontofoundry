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

export type ConceptRef = { kind: "object_type" | "value_type" | "builtin" | "any"; ref: string };
export type NativeRole = { id: string; name?: string | null; concept: ConceptRef; position?: number | null; native_presence?: string[]; origin?: "platform" | "imported" | "migrated"; client_ref?: null; implicit_owner?: boolean };
export type RoleConcept = { id: string; name?: string | null; concept: string; kind: ConceptRef["kind"] };
export type NativeFields = { native_presence?: string[]; position?: number | null; origin?: "platform" | "imported" | "migrated" };
export type NativeRelationFields = NativeFields & { owner_ref?: ConceptRef; roles?: NativeRole[]; owner_role_id?: string; all_roles?: NativeRole[]; role_concepts?: RoleConcept[]; readonly?: boolean; endpoint_direction?: "forward" | "reverse"; owner_role_name?: string | null; legacy_multiplicity?: string | null };
export type LegacyMappingForm = { mappings: DataMapping[]; joins: Record<string, { source_column: string; target_column: string } | null> };

export type AttributeDefinition = {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  value_kind: string;
  required: boolean;
  identifier: boolean;
  value_concept?: string | null;
  target_role_name?: string | null;
  multiplicity?: "one_to_one" | "many_to_one" | null;
  // Ossie relationship fields: constraints, derivations and readings.
  requires?: string[];
  derived_by?: string[];
  verbalizes?: string[];
  declared_by?: string;
};

export type ObjectType = {
  id: string;
  kind: "object_type";
  name: string;
  technical_name: string;
  description: string;
  tags: string[];
  extends?: string[];
  requires?: string[];
  derived_by?: string[];
  attributes: AttributeDefinition[];
  attribute_count: number;
  supertypes?: { id: string; name: string; technical_name: string }[];
  inherited_attributes?: AttributeDefinition[];
};

export type LinkType = NativeRelationFields & {
  id: string;
  kind: "link_type";
  name: string;
  technical_name: string;
  description: string;
  tags: string[];
  source_type_id: string;
  target_type_id: string;
  source_role_name?: string | null;
  target_role_name?: string | null;
  multiplicity: string;
  attribute_count: 0;
  identifier?: boolean;
  requires?: string[];
  derived_by?: string[];
  verbalizes?: string[];
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
  kind: "object_type" | "value_type" | "link_type";
  label: string;
  technical_name: string;
  description: string;
  tags: string[];
  roles?: NativeRole[];
  all_roles?: NativeRole[];
  verbalizes?: string[];
  owner_ref?: ConceptRef;
  attribute_count?: number;
  value_kind?: string;
  identifier?: boolean;
};

export type GraphEdge = {
  id: string;
  kind: "attribute" | "link_type" | "extends" | "role";
  label: string;
  technical_name: string;
  source: string;
  target: string;
  link_type_id?: string;
  role_id?: string;
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

// --- Draft views -------------------------------------------------------------
// Components read drafts through DraftView: types carry their own properties as
// `attributes` and their rules as `requires`/`derived_by`, which is how the UI
// presents them. Only lib/draftView converts between this and the stored Draft.
export type ObjectDefinition = Omit<ObjectType, "kind" | "attribute_count">;
export type LinkDefinition = Omit<LinkType, "kind" | "attribute_count">;
export type EvidenceLocator = {
  heading?: string | null;
  line_start: number;
  line_end: number;
};
/** Stored shape, exactly as in drafts and version snapshots. */
export type MaterialEvidence = {
  kind: "material";
  id: string;
  material_id: string;
  material_sha256: string | null;
  locator: EvidenceLocator;
  quote: string;
};
export type ManualEvidence = {
  kind: "manual";
  id: string;
  note: string;
  created_by: string;
  created_at: string;
};
export type Evidence = MaterialEvidence | ManualEvidence;
/** Detail DTO shape: the server adds the material name for display. */
export type EvidenceView =
  | (MaterialEvidence & { material_name: string; material_archived: boolean })
  | ManualEvidence;
export type MaterialObject = {
  id: string;
  type_id: string;
  name: string;
  values: Record<string, string | number | boolean | null>;
  evidence: Evidence[];
};
export type MaterialLink = NativeRelationFields & {
  id: string;
  type_id: string;
  source_id: string | null;
  target_id: string | null;
  role_values?: { role_id: string; object_id?: string | null; value?: unknown }[];
  evidence: Evidence[];
};
export type DataMapping = {
  id: string;
  type_id: string;
  // The data source's name, not a connection id: the published model carries no
  // credentials, and the workspace binds the name to a connection at query time.
  connection_alias: string;
  table_name: string;
  schema_name: string | null;
  key_column: string;
  fields: Record<string, string>;
};
export type DraftView = {
  workspace_id: string;
  requires: string[];
  object_types: ObjectDefinition[];
  link_types: LinkDefinition[];
  objects: MaterialObject[];
  links: MaterialLink[];
  mappings: DataMapping[];
};

// --- Stored draft (schema v2) ------------------------------------------------
export type ObjectTypeElement = NativeFields & {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  tags: string[];
  extends: string[];
  evidence: Evidence[];
};
export type PropertyElement = Omit<
  AttributeDefinition,
  "requires" | "derived_by" | "declared_by"
> & NativeRelationFields & { owner_type_id: string; evidence: Evidence[] };
export type LinkTypeElement = Omit<LinkDefinition, "requires" | "derived_by"> & {
  evidence: Evidence[];
};
export type RuleElement = {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  owner_kind: "object_type" | "value_type" | "property" | "link_type" | "action";
  owner_id: string;
  rule_kind: "constraint" | "derivation";
  expression: string;
  verbalizes: string[];
  evidence: Evidence[];
};
export type ActionElement = {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  input_type_id: string;
  parameters: {
    id: string;
    name: string;
    technical_name: string;
    value_kind: string;
    required: boolean;
  }[];
  precondition_rule_ids: string[];
  effects: {
    id: string;
    kind: "set_property" | "create_link" | "delete_link";
    property_id: string | null;
    link_type_id: string | null;
    expression: string;
  }[];
  evidence: Evidence[];
};
export type LegacyDraft = {
  schema_version: "2";
  workspace_id: string;
  ontology_requires: string[];
  object_types: ObjectTypeElement[];
  properties: PropertyElement[];
  link_types: LinkTypeElement[];
  rules: RuleElement[];
  actions: ActionElement[];
  material_objects: MaterialObject[];
  material_links: MaterialLink[];
  mappings: DataMapping[];
};
export type NativeConcept = Omit<ObjectTypeElement, "extends" | "description"> & { concept: string; description: string | null; extends: ConceptRef[]; identify_by: string[]; requires: string[]; derived_by: string[] };
export type NativeLink = Omit<LinkTypeElement, "source_type_id" | "target_type_id" | "multiplicity" | "description" | "data_join"> & { owner_ref: ConceptRef; roles: NativeRole[]; multiplicity: "ManyToOne" | "OneToOne" | null; description: string | null; requires: string[]; derived_by: string[] };
export type NativeProperty = NativeLink & { value_kind: string; required: boolean; identifier: boolean; owner_type_id?: never };
export type NativeDraft = Omit<LegacyDraft, "schema_version" | "object_types" | "properties" | "link_types"> & {
  schema_version: "3"; hash_algorithm: "ontofoundry-domain-v3";
  object_types: NativeConcept[]; value_types: NativeConcept[];
  properties: NativeProperty[]; link_types: NativeLink[];
  document_origin: "platform" | "imported" | "migrated"; native_presence: string[];
  ossie_version: string; ossie_name: string | null; ossie_description: string | null; ai_context: unknown;
  semantic_models: { id: string; [key: string]: unknown }[];
  datasets: unknown[]; dataset_fields: unknown[]; dataset_relationships: unknown[]; metrics: unknown[];
  concept_mappings: unknown[]; mapping_nodes: unknown[];
  core_version?: string | null; core_presence?: string[]; extension_v4: Record<string, unknown>;
  /** Client-only copy of the existing mapping form; excluded from draft JSON. */
  _legacy_form?: LegacyMappingForm;
};
export type Draft = LegacyDraft | NativeDraft;

// --- Proposals (frontend contract §4) ---------------------------------------
export type TargetKind =
  | "value_type"
  | "object_type"
  | "property"
  | "link_type"
  | "rule"
  | "action"
  | "material_object"
  | "material_link"
  | "mapping";

export type ProposalStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "stale"
  | "conflict"
  | "superseded";

export type FieldChange = { path: string; before: unknown; after: unknown };

export type ElementChange = {
  element_kind: TargetKind;
  element_id: string;
  label: string;
  owner_label?: string | null;
  change: "created" | "updated" | "deleted";
  field_changes: FieldChange[];
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

export type ProposalItem = {
  id: string;
  batch_id: string;
  ordinal: number;
  client_ref: string | null;
  operation: "create" | "update" | "delete";
  target_kind: TargetKind;
  target_id: string;
  display_name: string;
  owner_label?: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  field_changes: FieldChange[];
  evidence: EvidenceView[];
  reason: string;
  depends_on: string[];
  dependency_group: string[];
  status: ProposalStatus;
  stored_status: "pending" | "accepted" | "rejected" | "superseded";
  status_reason?: string;
  accepted_revision?: number | null;
  decided_at?: string | null;
};

export type ProposalBatch = {
  id: string;
  status: "validating" | "available" | "failed";
  created_at: string;
  source_session_revision: number;
  base_version_id: string | null;
  counts: Record<ProposalStatus, number>;
  error?: { code: string; message: string } | null;
};

export type ProposalBatchDetail = ProposalBatch & { items: ProposalItem[] };

export type DecisionResult = {
  session: ModelingSession;
  results: { proposal_id: string; status: ProposalStatus; reason?: string }[];
  validation: VersionSummary["validation"];
};

export type MergeConflict = {
  key: string;
  element_kind: TargetKind | null;
  element_id: string | null;
  element_label: string;
  path: string;
  kind: "field" | "delete_modify" | "duplicate_name" | "dangling_reference";
  base: unknown;
  latest: unknown;
  draft: unknown;
  allowed: ("latest" | "draft" | "custom" | "both")[];
};

export type Resolution = { choice: "latest" | "draft" | "custom" | "both"; value?: unknown };

export type Impact = {
  element_kind: TargetKind;
  element_id: string;
  label: string;
  reason: string;
};

export type PublishPreview = {
  session_revision: number;
  base_version_id: string | null;
  /** The version the session started from; null for a blank start. */
  base_version_number: number | null;
  current_version_id: string | null;
  current_version_number: number | null;
  next_version_number: number;
  current_version_sha256: string;
  merged_snapshot_sha256: string;
  /** Actual merged v2 snapshot, including changes from other sessions. */
  merged_model?: Draft;
  validation: VersionSummary["validation"];
  changes: ElementChange[];
  /** Workspace constraints publishing changes; null when unchanged. */
  requires_change: { before: string[]; after: string[] } | null;
  /** Display labels by element id, across the current version and the merge. */
  labels: Record<string, string>;
  impacts: Impact[];
  auto_merged: (ElementChange & { side: "latest" | "both" })[];
  ossie: Record<string, unknown> | null;
};

export type Candidate = {
  id: string;
  status: string;
  reason: string;
  conflict?: string;
  evidence?: Evidence[];
  /**
   * The draft value this proposal was computed against. accept_candidates
   * compares against it to detect hand edits — without it every acceptance
   * would read as a conflict.
   */
  before?: unknown;
  source_task_id?: string;
} & (
  | { kind: "object_type"; value: ObjectDefinition }
  | { kind: "link_type"; value: LinkDefinition }
  | { kind: "object"; value: MaterialObject }
  | { kind: "link"; value: MaterialLink }
  | { kind: "mapping"; value: DataMapping }
  | { kind: "clarification"; value: { name: string } }
);
export type ModelingSession = {
  id: string;
  title: string;
  workspace_id: string;
  base_version_id: string | null;
  revision: number;
  draft: Draft;
  draft_sha256?: string;
  base_version_sha256?: string;
  pending_proposal_count?: number;
  latest_batch_id?: string | null;
  base_diff?: ElementChange[];
  graph: TypeGraph;
  candidates: Candidate[];
  material_ids: string[];
  task_status: string;
  task_detail: string;
  /**
   * Non-blocking import notes from the complete model produced by the last run.
   */
  result_warnings?: string[];
  dataagent_topic_id?: string | null;
  dataagent_task_id?: string | null;
  updated_at: string;
  validation?: VersionSummary["validation"];
};
export type ModelingSessionSummary = Pick<
  ModelingSession,
  "id" | "title" | "task_status" | "updated_at"
>;
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
    mappings_added?: number;
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
export type DataAgentHealth = {
  ok: boolean;
  checks: {
    name: string;
    ok: boolean;
    message: string;
    hint: string;
  }[];
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
