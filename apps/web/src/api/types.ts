// REST types for the core-1 API. Core element shapes come from the generated
// core.generated.ts; the read projections and envelopes below follow
// docs/plans/2026-10-16-core1-p2-api-contract.md.
import type * as Core from "./core.generated";

/** The server always fills defaults, so stored elements carry every field. */
type Stored<T> = { [K in keyof T]-?: T[K] };

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
export type Dataset = Stored<Core.Dataset>;
export type DatasetColumn = Core.DatasetColumn;
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
  | "material_link";

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
  | "material_links";

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

export type MetricRead =
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
  | (ExpressionMetric & { binding_status: BindingStatus; sql_reference?: SQLReference });

export type ForbiddenMetricRead = {
  id: UUID;
  name: string;
  technical_name: string;
  description?: string;
  synonyms?: string[];
  binding_status: "forbidden";
};

export type Effective<T> = T & { inherited_from: UUID | null; binding_status: BindingStatus };
export type PropertyRead = Effective<Property> & {
  binding?: FieldBinding;
  physical_type?: string | null;
};
export type LinkRead = Effective<LinkType> & { direction: "forward" | "reverse" };
export type MappingRead = DataMapping & { binding_status: BindingStatus };

export type ObjectTypeRead = ObjectType & {
  properties: PropertyRead[];
  links: LinkRead[];
  rules: Effective<Rule>[];
  child_types: Pick<ObjectType, "id" | "name" | "technical_name">[];
  binding_status: BindingStatus;
  mapping?: MappingRead | null;
  instance_source_type_ids?: UUID[];
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
  technical_name: string;
  description: string;
  tags: string[];
  attribute_count?: number;
};
export type GraphEdge = {
  id: string;
  kind: "link_type" | "extends";
  label: string;
  technical_name: string;
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
> & { has_unpublished_changes: boolean };

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
export type ElementSaveKind = "object_type" | "link_type" | "metric" | "dataset" | "mapping";
export type ElementSave = {
  target_kind: ElementSaveKind;
  target_id: UUID;
  expected_current_version_id: UUID | null;
  session_id?: UUID | null;
  expected_session_revision?: number | null;
  draft: Draft;
  affected_items?: AffectedItem[];
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
  comment?: string | null;
  missing: boolean;
  datasets: DatasetRead[];
};
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
