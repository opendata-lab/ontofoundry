// REST types for the core-1 API. Core element shapes come from the generated
// core.generated.ts; the read projections and envelopes below follow
// docs/plans/2026-10-16-core1-p2-api-contract.md.
import type * as Core from "./core.generated";

/** The server always fills defaults, so stored elements carry every field. */
type Stored<T> = { [K in keyof T as K extends "display_name" ? never : K]-?: T[K] }
  & Pick<T, Extract<keyof T, "display_name">>;

export type UUID = string;
export type ISODate = string;
export type ISOTime = string;
export type SHA256 = string;
export type Scalar = string | number | boolean | null;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export type ValueKind = Core.ValueKind;
export type ObjectType = Stored<Core.ObjectType>;
export type Property = Stored<Core.Property>;
export type LinkType = Stored<Core.LinkType>;
export type Rule = Stored<Core.Rule>;
export type ValueType = Stored<Core.ValueType>;
export type Dataset = Stored<Core.Dataset>;
export type DatasetColumn = Core.DatasetColumn;
export type BindingMode = Core.BindingMode;
export type DataMapping = Stored<Core.DataMapping>;
export type MappingSource = Stored<Core.MappingSource>;
export type ColumnBinding = Core.ColumnBinding;
export type ExpressionBinding = Core.ExpressionBinding;
export type FieldBinding = ColumnBinding | ExpressionBinding;
export type DirectJoin = Core.DirectJoin;
export type MappingTableJoin = Core.MappingTableJoin;
export type DataJoin = DirectJoin | MappingTableJoin;
export type SimpleMetric = Stored<Core.SimpleMetric>;
export type RatioMetric = Stored<Core.RatioMetric>;
export type ExpressionMetric = Stored<Core.ExpressionMetric>;
export type Metric = SimpleMetric | RatioMetric | ExpressionMetric;
export type ColumnReference = Core.ColumnReference;
export type Condition = Core.Condition;
export type Operator = Core.Condition["operator"];
export type Aggregation = Core.SimpleMetric["aggregation"];
export type Path = Core.Path;
export type LinkStep = Core.LinkStep;
export type PathCondition = Core.PathCondition;
export type DerivedSimple = Core.DerivedSimple;
export type DerivedExpression = Core.DerivedExpression;
export type DerivedBranch = DerivedSimple | DerivedExpression;
export type MaterialObject = Stored<Core.MaterialObject>;
export type MaterialLink = Stored<Core.MaterialLink>;
export type MaterialEvidence = Core.MaterialEvidence;
export type ManualEvidence = Core.ManualEvidence;
export type EvidenceLocator = Core.EvidenceLocator;
export type Evidence = MaterialEvidence | ManualEvidence;

export type TargetKind =
  | "object_type"
  | "property"
  | "link_type"
  | "rule"
  | "metric"
  | "dataset"
  | "mapping"
  | "material_object"
  | "material_link"
  | "value_type";

export type ElementByKind = {
  object_type: ObjectType;
  property: Property;
  link_type: LinkType;
  rule: Rule;
  metric: Metric;
  dataset: Dataset;
  mapping: DataMapping;
  material_object: MaterialObject;
  material_link: MaterialLink;
  value_type: ValueType;
};
export type CoreElement = ElementByKind[TargetKind];

export type CollectionKey =
  | "object_types"
  | "properties"
  | "link_types"
  | "rules"
  | "metrics"
  | "datasets"
  | "mappings"
  | "material_objects"
  | "material_links"
  | "value_types";

export const COLLECTION_BY_KIND: Record<TargetKind, CollectionKey> = {
  object_type: "object_types",
  property: "properties",
  link_type: "link_types",
  rule: "rules",
  metric: "metrics",
  dataset: "datasets",
  mapping: "mappings",
  material_object: "material_objects",
  material_link: "material_links",
  value_type: "value_types",
};

/** A core-1 draft as the server returns it: all nine collections present. */
export type Draft = {
  schema_version: "core-1";
  workspace_id: UUID;
  object_types: ObjectType[];
  properties: Property[];
  link_types: LinkType[];
  rules: Rule[];
  metrics: Metric[];
  datasets: Dataset[];
  mappings: DataMapping[];
  material_objects: MaterialObject[];
  material_links: MaterialLink[];
  value_types: ValueType[];
};

export type Page<T> = { total: number; items: T[]; next_cursor: string | null };
export type Items<T> = { items: T[] };

// --- errors ---------------------------------------------------------------

export type ValidationIssue = {
  code?: string;
  message: string;
  path?: string;
  element_id?: UUID;
  element_kind?: TargetKind;
};

export type ValidationReport = {
  standard: "core-1";
  schema_status: "passed" | "failed";
  semantic_status: "passed" | "failed";
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  publishable: boolean;
};

// --- workspaces, versions, read projections -------------------------------

export type User = {
  id: UUID;
  subject: string;
  display_name: string;
  email: string | null;
};

export type Workspace = {
  id: UUID;
  slug: string;
  name: string;
  description: string;
  role: "admin" | "member" | null;
  visibility: "member" | "published_only";
  current_version: number | null;
  version_id: UUID | null;
  version_sha256: SHA256 | null;
  object_type_count: number;
  link_type_count: number;
  updated_at: ISOTime;
};

export type Counts = {
  object_types: number;
  link_types: number;
  attributes: number;
  rules: number;
  metrics: number;
  datasets?: number;
  mappings?: number;
  material_objects?: number;
  material_links?: number;
};

export type VersionEnvelope = {
  workspace_id: UUID;
  version_id: UUID;
  version_sha256: SHA256;
  version_content_sha256: SHA256;
  normalized_snapshot_sha256: SHA256;
};

export type VersionSummary = VersionEnvelope & {
  version: number;
  status: "published";
  message: string;
  published_at: ISOTime;
  validation: ValidationReport;
  counts: Counts;
};

export type BindingStatus =
  | "bound"
  | "unbound"
  | "virtual"
  | "missing_key"
  | "cross_connection"
  | "metadata_stale"
  | "forbidden";

export type SQLReference = {
  sql: string;
  params: Record<string, Scalar>;
  dialect: string;
  database: string;
  note?: string;
};

export type DatasetRead = Dataset & {
  binding_status: BindingStatus;
  database?: string;
  schema?: string | null;
  metadata_snapshot_id?: string | null;
  observed_at?: ISOTime | null;
};

export type MetricRead = (
  | (SimpleMetric & {
      value_kind: ValueKind | null;
      binding_status: BindingStatus;
      sql_reference?: SQLReference;
    })
  | (RatioMetric & {
      dataset_id: UUID;
      value_kind: "decimal";
      binding_status: BindingStatus;
      components: { numerator: SimpleMetric; denominator: SimpleMetric };
      sql_reference?: SQLReference;
    })
  | (ExpressionMetric & { binding_status: BindingStatus; sql_reference?: SQLReference })
) & {
  datasets?: DatasetRead[];
  effective_bindings?: EffectiveBindingRead[];
};

export type ForbiddenMetricRead = {
  id: UUID;
  display_name?: string | null;
  name: string;
  description?: string;
  synonyms?: string[];
  binding_status: "forbidden";
};

export type Effective<T> = T & { inherited_from: UUID | null; binding_status: BindingStatus };
export type PropertyRead = Effective<Property> & {
  binding?: FieldBinding;
  physical_type?: string | null;
};
export type MembershipRead = {
  type_id: UUID;
  mapping_id: UUID;
  binding_mode: BindingMode;
  membership_source_id: string | null;
  derived_by: DerivedBranch[];
};
export type EffectiveLinkRead = {
  link_type_id: UUID;
  source_type_id: UUID;
  target_type_id: UUID;
  data_join: DataJoin | null;
};
export type EffectiveBindingRead = {
  type_id: UUID;
  sources: MappingSource[];
  fields: Record<string, FieldBinding>;
  memberships: MembershipRead[];
  links: EffectiveLinkRead[];
};
export type LinkRead = Effective<LinkType> & {
  direction: "forward" | "reverse";
  effective_bindings?: EffectiveBindingRead[];
  datasets?: DatasetRead[];
};
export type MappingRead = DataMapping & { binding_status: BindingStatus };

export type ObjectTypeRead = ObjectType & {
  properties: PropertyRead[];
  links: LinkRead[];
  rules: Effective<Rule>[];
  child_types: Pick<ObjectType, "id" | "display_name" | "name">[];
  binding_status: BindingStatus;
  mapping?: MappingRead | null;
  instance_source_type_ids?: UUID[];
  effective_bindings?: EffectiveBindingRead[];
  datasets?: DatasetRead[];
  sources?: MappingSource[];
};

/** The outer kind names the resource; definition.kind keeps the metric union. */
export type ResourceRead =
  | { kind: "object_type"; definition: ObjectTypeRead }
  | { kind: "link_type"; definition: LinkRead }
  | { kind: "metric"; definition: MetricRead | ForbiddenMetricRead }
  | { kind: "dataset"; definition: DatasetRead };
export type ResourceKind = ResourceRead["kind"];

export type TypeList = VersionEnvelope & Items<ResourceRead> & {
  next_cursor: null;
  ambiguous: boolean;
};
export type TypeDetail = VersionEnvelope &
  (
    | { ambiguous: false; item: ResourceRead }
    | { ambiguous: true; item: null; candidates: ResourceRead[] }
  );

export type GraphNode = {
  id: UUID;
  kind: "object_type";
  label: string;
  name: string;
  description: string;
  tags: string[];
  attribute_count?: number;
};
export type GraphEdge = {
  id: string;
  kind: "link_type" | "extends";
  label: string;
  name: string;
  source: UUID;
  target: UUID;
  link_type_id?: UUID;
  multiplicity?: LinkType["multiplicity"];
  description?: string;
  tags?: string[];
};
export type TypeGraph = VersionEnvelope & { nodes: GraphNode[]; edges: GraphEdge[] };

export type WorkspaceOverview = {
  version: VersionSummary | null;
  graph: TypeGraph | null;
  details: null | {
    object_count?: number;
    link_count?: number;
    evidence_material_count?: number;
    mapping_count?: number;
    objects?: Pick<DocumentFactRead, "id" | "type_id" | "display_text">[];
    links?: Pick<MaterialLink, "id" | "type_id" | "source_id" | "target_id">[];
    mappings?: { id: UUID; type_id: UUID; binding_status: BindingStatus }[];
  };
};

// --- sessions, diffs, publishing ------------------------------------------

export type FieldChange = { path: string; before: Json; after: Json };
export type ElementChange = {
  element_kind: TargetKind;
  element_id: UUID;
  label: string;
  owner_label?: string | null;
  change: "created" | "updated" | "deleted";
  field_changes: FieldChange[];
  before: CoreElement | null;
  after: CoreElement | null;
};

export type ModelingSession = {
  import_source?: ImportSource | null;
  id: UUID;
  workspace_id: UUID;
  title: string;
  base_version_id: UUID | null;
  revision: number;
  draft: Draft;
  draft_sha256: SHA256;
  base_version_sha256: SHA256;
  pending_proposal_count: number;
  latest_batch_id: UUID | null;
  base_diff: ElementChange[];
  graph: Omit<TypeGraph, "version_id"> & { version_id: UUID | "" };
  material_ids: string[];
  /** Registered tables linked to the session; the agent proposes datasets on them. */
  linked_tables?: LinkedTable[];
  task_status: string;
  task_detail: string;
  dataagent_topic_id: string | null;
  dataagent_task_id: string | null;
  dataagent_task_mode?: string | null;
  dataagent_run_token?: string | null;
  uploaded_material_ids?: string[];
  last_result_task_id?: string | null;
  result_state?: string;
  result_warnings?: string[];
  result_claimed_at?: ISOTime | null;
  updated_at: ISOTime;
  validation?: ValidationReport;
};

export type ModelingSessionSummary = Pick<
  ModelingSession,
  "id" | "title" | "task_status" | "updated_at" | "base_version_id"
> & { has_unpublished_changes: boolean; import_source?: ImportSource | null };

export type MergeConflict = {
  key: string;
  element_kind: TargetKind | null;
  element_id: UUID | null;
  element_label: string;
  path: string;
  kind: "field" | "delete_modify" | "duplicate_name" | "dangling_reference";
  base: Json;
  latest: Json;
  draft: Json;
  allowed: ("latest" | "draft" | "custom" | "both")[];
};
export type Resolution = { choice: "latest" | "draft" | "custom" | "both"; value?: Json };
export type Impact = { element_kind: TargetKind; element_id: UUID; label: string; reason: string };

export type PublishPreview = {
  session_revision: number;
  base_version_id: UUID | null;
  base_version_number: number | null;
  current_version_id: UUID | null;
  current_version_number: number | null;
  next_version_number: number;
  current_version_sha256: SHA256;
  merged_snapshot_sha256: SHA256;
  merged_model: Draft;
  validation: ValidationReport;
  changes: ElementChange[];
  labels: Record<UUID, string>;
  impacts: Impact[];
  auto_merged: (ElementChange & { side: "latest" | "both" })[];
  dataset_checks?: { dataset_id: UUID; name: string; display_name: string | null; valid: boolean; diagnostics: DatasetDiagnostic[] }[];
};
export type PublishResult = { version: VersionSummary; session: ModelingSession };

export type Comparison = {
  left: VersionSummary | null;
  right: VersionSummary;
  changes: { path: string; kind: "added" | "removed" | "changed"; before: Json; after: Json }[];
  impacts: { kind: TargetKind; id: UUID; label: string }[];
};

export type AffectedItem = {
  target_kind: TargetKind;
  target_id: UUID;
  expected_target_hash: SHA256;
};
export type ElementSaveKind = "object_type" | "link_type" | "metric" | "dataset" | "mapping" | "value_type";
export type ElementSave = {
  target_kind: ElementSaveKind;
  target_id: UUID;
  expected_current_version_id: UUID | null;
  session_id?: UUID | null;
  expected_session_revision?: number | null;
  draft: Draft;
  affected_items?: AffectedItem[];
};
export type ElementSaveImpact = {
  current_version_id: UUID | null;
  session_revision: number | null;
  affected_items: (AffectedItem & { reason: string })[];
};
export type ElementSaveResult = {
  version: VersionSummary;
  draft: Draft;
  session: ModelingSession | null;
};

// --- proposals ------------------------------------------------------------

export type ProposalStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "stale"
  | "conflict"
  | "superseded";
export type EvidenceView = Evidence & { material_name?: string; material_archived?: boolean };
export type DuplicateCandidate = {
  id: UUID;
  type_id: UUID;
  display_text: string;
  expected_target_hash: SHA256;
};
export type ProposalItem = {
  source_diagnostics?: DatasetDiagnostic[];
  id: UUID;
  batch_id: UUID;
  ordinal: number;
  client_ref: string | null;
  operation: "create" | "update" | "delete";
  target_kind: TargetKind;
  target_id: UUID;
  display_name: string;
  owner_label: string | null;
  before: CoreElement | null;
  after: CoreElement | null;
  field_changes: FieldChange[];
  evidence: EvidenceView[];
  reason: string;
  depends_on: UUID[];
  dependency_group: UUID[];
  atomic_group_id: UUID | null;
  duplicate_candidates: DuplicateCandidate[];
  status: ProposalStatus;
  stored_status: "pending" | "accepted" | "rejected" | "superseded";
  status_reason: string;
  accepted_revision: number | null;
  decided_at: ISOTime | null;
};
export type ProposalBatch = {
  producer?: { kind?: string; adapter?: string; report_id?: UUID; issue_id?: UUID };
  id: UUID;
  status: "validating" | "available" | "failed";
  created_at: ISOTime;
  source_session_revision: number;
  base_version_id: UUID | null;
  counts: Record<ProposalStatus, number>;
  error: { code: string; message: string } | null;
};
export type ProposalBatchDetail = ProposalBatch & { items: ProposalItem[] };
export type Decision = { proposal_id: UUID; decision: "accept" | "reject" | "restore" };
export type DecisionResult = {
  session: ModelingSession;
  results: { proposal_id: UUID; status: ProposalStatus; reason?: string }[];
  validation: ValidationReport;
};
export type FactProposalRevision = {
  expected_session_revision: number;
  target_id: UUID;
  expected_target_hash: SHA256;
  after: MaterialObject;
  reason?: string;
};

// --- data catalog, datasets, mapping preview ------------------------------

export type DataConnection = {
  id: UUID;
  name: string;
  kind: "mysql" | "doris" | "postgresql";
  host: string;
  port: number;
  database: string;
  username: string;
};
export type CatalogColumn = {
  name: string;
  type: string;
  primary_key: boolean;
  nullable?: boolean | null;
  comment?: string | null;
};
export type DataTable = { name: string; schema: string | null; columns: CatalogColumn[] };
export type SchemaChange = {
  table: string;
  column: string | null;
  kind: "added" | "removed" | "changed";
  before: Json;
  after: Json;
};
export type AssetTable = DataTable & {
  kind?: "table" | "view";
  primary_key?: string[];
  observed_at?: ISOTime | null;
  comment?: string | null;
  missing: boolean;
  datasets: DatasetRead[];
};
export type TableRows = { columns: string[]; items: Record<string, Json>[]; limit: number };
export type Assets = {
  connection_id: UUID;
  version_id: UUID | null;
  items: AssetTable[];
  metadata_snapshot_id: string | null;
  observed_at: ISOTime | null;
  error: string | null;
  changes: SchemaChange[];
  status: "ready" | "stale" | "unobserved";
};

export type TypedKeyPart =
  | { type: "string"; value: string }
  | { type: "integer"; value: string }
  | { type: "decimal"; value: string }
  | { type: "float"; value: number }
  | { type: "boolean"; value: boolean }
  | { type: "date"; value: ISODate }
  | { type: "datetime"; value: ISOTime };
export type TypedKey = TypedKeyPart[];
export type SnapshotDates = { dataset_id: UUID; date: ISODate | null }[];

export type MappingPreviewRequest = {
  mapping: DataMapping;
  session_id?: UUID;
  q?: string;
  key?: TypedKey;
  offset?: number;
  limit?: number;
  snapshot_date?: ISODate;
};
export type MappingPreview = {
  items: {
    __key: TypedKey;
    __type_id: UUID;
    __ref: string;
    values: Record<string, Scalar>;
    display_text: string;
  }[];
  has_more: boolean;
  source: "database";
  snapshot_dates: SnapshotDates;
};

// --- instances ------------------------------------------------------------

export type DocumentFactRead = MaterialObject & {
  ref: string;
  source: "document";
  display_text: string;
};
export type DatabaseInstanceRead = {
  id: string;
  ref: string;
  type_id: UUID;
  key: TypedKey;
  source: "database";
  display_text: string;
  values: Record<string, Scalar>;
  evidence: [];
};
export type InstanceRead = DocumentFactRead | DatabaseInstanceRead;
export type InstanceEnvelope = VersionEnvelope & {
  queried_at: ISOTime;
  data_mode: "live" | "snapshot";
  quality_issues: ValidationIssue[];
};
export type InstanceList = InstanceEnvelope & {
  items: InstanceRead[];
  source: "document" | "database";
  next_cursor: string | null;
  truncated: boolean;
  snapshot_dates: SnapshotDates;
};
export type InstanceDetail = InstanceEnvelope & {
  item: InstanceRead;
  snapshot_dates: SnapshotDates;
};
export type InstanceLinkRead = {
  id: string;
  type_id: UUID;
  source_id: string;
  target_id: string;
  evidence: Evidence[];
};
export type InstanceNeighborhood = {
  center_id: string;
  objects: InstanceRead[];
  links: InstanceLinkRead[];
  warnings: string[];
  truncated: boolean;
  source: "document" | "database";
  depth: number;
  snapshot_dates: SnapshotDates;
};
export type NeighborhoodRequest = {
  type_id: UUID;
  key: TypedKey;
  session_id?: UUID;
  depth?: number;
  snapshot_date?: ISODate;
};

// --- metric preview -------------------------------------------------------

export type MetricPreviewRequest = {
  session_id?: UUID;
  expected_session_revision?: number;
  expected_current_version_id?: UUID | null;
  metric: Metric;
  components?: SimpleMetric[];
  time_range?: { start: ISOTime | ISODate; end: ISOTime | ISODate };
  trend_grain?: "month";
};
export type MetricPreviewReason =
  | "expression_not_supported"
  | "engine_not_supported"
  | "binding_not_ready"
  | "source_ambiguous"
  | "forbidden"
  | "query_timeout"
  | "query_failed";
export type MetricPreview = {
  definition_hash: SHA256;
  context_version: UUID | null;
  session_revision: number | null;
  status: "ok" | "unable";
  reason_code?: MetricPreviewReason | string;
  reason?: string;
  value: Scalar;
  value_kind: ValueKind | null;
  total_query: SQLReference | null;
  trend_query?: SQLReference | null;
  trend?: { period: ISODate; value: Scalar }[];
  snapshot_dates: { dataset_id: UUID; period: ISODate | null; date: ISODate | null }[];
  warnings: string[];
};

// --- unchanged auxiliary resources ----------------------------------------

export type Material = {
  id: string;
  name: string;
  byte_size: number;
  chunk_count: number;
  sha256: SHA256;
  created_at?: ISOTime;
  archived_at?: ISOTime | null;
};
export type MaterialUsage = {
  object_types: number;
  link_types: number;
  properties: number;
  rules: number;
  metrics: number;
  material_objects: number;
  material_links: number;
  references: string[];
  can_delete: boolean;
};
export type ManagedMaterial = Material & { usage: MaterialUsage };
export type Capabilities = {
  agent_configured: boolean;
  model: string;
  max_file_mb: number;
  connections_configured: boolean;
  skills: string[];
};
export type DataAgentHealth = {
  ok: boolean;
  checks: { name: string; ok: boolean; message: string; hint: string }[];
};
export type Member = {
  id: number;
  user_id: UUID;
  name: string;
  subject: string;
  role: "admin" | "member";
};
export type Scope = "ontology:read" | "mappings:read" | "instances:read";
export type ServiceToken = { id: UUID; name: string; created_at: ISOTime; scopes: Scope[] };

// --- MCP read projection --------------------------------------------------

export type ToolName = "search_ontology" | "get_ontology" | "search_objects" | "get_object";
export type MCPMeta = { _meta?: Record<string, Json> };
export type ToolArguments =
  | { name: "search_ontology"; arguments: SearchOntologyArgs }
  | { name: "get_ontology"; arguments: GetOntologyArgs }
  | { name: "search_objects"; arguments: SearchObjectsArgs }
  | { name: "get_object"; arguments: GetObjectArgs };
export type MCPRequest = { jsonrpc: "2.0"; id: string | number } & (
  | {
      method: "initialize";
      params: MCPMeta & {
        protocolVersion: string;
        capabilities: Record<string, Json>;
        clientInfo: { name: string; version: string };
      };
    }
  | { method: "tools/list" | "ping" | "server/discover"; params?: MCPMeta }
  | { method: "tools/call"; params: MCPMeta & ToolArguments }
);
export type MCPNotification = {
  jsonrpc: "2.0";
  method: "notifications/initialized";
  params?: MCPMeta;
};
export type ToolDescription = {
  name: ToolName;
  description: string;
  inputSchema: Record<string, Json>;
  annotations: { readOnlyHint: true; destructiveHint: false };
};
export type MCPResponse<T> = { jsonrpc: "2.0"; id: string | number | null } & (
  | { result: T }
  | { error: { code: number; message: string; data?: Json } }
);
export type OntologyKind = "object_type" | "property" | "link_type" | "rule" | "metric";
export type Paging = { cursor?: string; limit?: number };
export type SearchOntologyArgs = Paging & { query: string; kinds?: OntologyKind[] };
export type GetOntologyArgs = Paging & {
  ids?: UUID[];
  kinds?: OntologyKind[];
  include?: ("semantic" | "physical" | "rules" | "adjacency")[];
};
export type SearchObjectsArgs = Paging & { type_id?: UUID; q?: string };
export type GetObjectArgs = Paging & {
  id: UUID;
  include?: ("properties" | "evidence" | "adjacency")[];
};
export type FieldSegment = {
  element_id: UUID;
  field: string;
  start: number;
  end: number;
  total: number;
  text: string;
  next_cursor: string | null;
};
export type MCPEnvelope = {
  workspace_id: UUID;
  version_id: UUID | null;
  field_segments?: FieldSegment[];
};
export type OntologyHit = {
  id: UUID;
  kind: OntologyKind;
  display_name?: string | null;
  name: string;
  summary: string;
  matched_synonyms: string[];
  owner_kind?: "object_type" | "property" | "link_type";
  owner_id?: UUID;
  dataset?: Pick<Dataset, "id" | "name">;
};
export type MCPList<T> = MCPEnvelope & Page<T>;
export type MCPObjectHit = Pick<DocumentFactRead, "id" | "type_id" | "display_text"> & {
  values: Record<string, Scalar>;
};
export type MCPAdjacency = {
  link_type_id: UUID;
  direction: "forward" | "reverse";
  source_id: UUID;
  target_id: UUID;
};
export type MCPObject = MCPObjectHit & {
  properties?: Page<{ property_id: UUID; value: Scalar }>;
  evidence?: Page<EvidenceView>;
  adjacency?: Page<MCPAdjacency>;
};
export type MCPElement = {
  id: UUID;
  kind: OntologyKind;
  display_name?: string | null;
  name: string;
  description?: string;
  synonyms?: string[];
  definition?: CoreElement;
  binding_status?: BindingStatus;
  inherited_from?: UUID | null;
  properties?: Page<PropertyRead>;
  rules?: Page<Effective<Rule>>;
  links?: Page<LinkRead>;
  child_types?: Page<Pick<ObjectType, "id" | "display_name" | "name">>;
  datasets?: Page<DatasetRead>;
  sources?: Page<MappingSource>;
  effective_bindings?: Page<EffectiveBindingRead>;
  components?: { numerator: SimpleMetric; denominator: SimpleMetric };
  dataset_id?: UUID;
  value_kind?: ValueKind | null;
  instance_source_type_ids?: UUID[];
  sql_reference?: SQLReference;
};
export type MCPGetOntology = MCPEnvelope & {
  total: number;
  elements: MCPElement[];
  missing: UUID[];
  next_cursor: string | null;
  field_segments?: FieldSegment[];
};
export type MCPCallResult<T> = {
  content: { type: "text"; text: string }[];
  structuredContent: T;
  isError?: boolean;
};

export type ImportSource = { adapter: string; report_id: UUID };
export type TranslationIssue = {
  id: UUID;
  outcome: "converted" | "dropped" | "error";
  construct: string;
  rule_id: string | null;
  severity: "info" | "warning" | "error";
  source_path: string;
  source_locator: { sha256?: string; formatted_sha256?: string; json_pointer?: string; line_start?: number; line_end?: number; line?: number; column?: number };
  original: string | null;
  target_element_ids: UUID[];
  completion_status: "not_needed" | "available";
  target_path: string | null;
  message: string;
};
export type TranslationReportData = {
  id: UUID;
  content_sha256: SHA256;
  direction: "import" | "export";
  adapter: string;
  counts: Record<string, number>;
  issues: TranslationIssue[];
};
export type ImportCompletion = {
  issue_id: UUID;
  message: string;
  original: string | null;
  source_path: string;
  source_locator: TranslationIssue["source_locator"];
  kind: "count_dataset" | "dataset_metadata" | "source_definition";
  dataset?: Dataset | null;
  datasets: { id: UUID; name: string }[];
  status: "available" | "proposed" | "accepted";
};
export type ImportConfirmed = { session_id: UUID; batch_id: UUID; report_id: UUID };
export type ImportPreview = {
  import_id: UUID;
  adapter: string;
  filename: string;
  report: TranslationReportData;
  content_sha256: SHA256;
  raw_sha256: SHA256;
  formatted_sha256: SHA256 | null;
  material_id: UUID | null;
  base_version_id: UUID | null;
  proposal_summary: { create: number; update: number; unchanged: number; blocked: { target_id: UUID; reason: string }[] };
  id_map: Record<UUID, UUID>;
  current_blocked: { target_id: UUID; reason: string }[];
  document_error: boolean;
  completion: ImportCompletion[];
  confirmed: ImportConfirmed | null;
};
export type ImportConfirm = { content_sha256: SHA256; expected_current_version_id: UUID | null; idempotency_key: string };
export type ImportCompletionRequest = {
  issue_id: UUID;
  expected_session_revision: number;
  expected_draft_sha256: SHA256;
  idempotency_key: string;
  dataset_id?: UUID | null;
  definition?: Record<string, unknown> | null;
  dataset?: Dataset | null;
};

export type ExportPreview = {
  version_id: UUID;
  adapter: string;
  report: TranslationReportData;
  content_sha256: SHA256 | null;
  filename: string;
  media_type: string;
  download_url: string | null;
};


export type DatasetDiagnostic = { code: string; severity: "error"; path: string; message: string; details?: { connection_id?: string; schema_name?: string; table_name?: string } };
export type DatasetCheckResult = { valid: boolean; diagnostics: DatasetDiagnostic[]; columns: DatasetColumn[] | null; referenced_tables: { schema_name: string | null; table_name: string }[] };
export type DatasetPreview = { columns: DatasetColumn[]; items: Record<string, unknown>[]; limit: number };
export type SyncJob = { id: string; connection_id: string; schema_name: string; scope: "all" | "selected"; state: "queued" | "running" | "succeeded" | "partial_failed" | "failed" | "interrupted"; total: number | null; processed: number; available: number; failed: number; error: string | null; duration_ms: number; batches: { id: string; ordinal: number; state: string; attempt: number; duration_ms: number; error: string | null; tables: string[]; results: { table_name: string; state: string; error?: string }[] }[] };

/** A synced table in data management that a modeling session may use. */
export type LinkedTable = { connection_id: string; schema_name: string; table_name: string };
export type RegisteredTable = LinkedTable & {
  connection_name: string;
  kind: string;
  comment: string;
  column_count: number;
  datasets: { id: string; name: string; display_name?: string | null }[];
};
