/* Generated from the core-1 Pydantic schema. Do not edit by hand. */

export type Columns = DatasetColumn[] | null
export type Comment = string
export type Name = string
export type PhysicalType = string | null
export type ConnectionId = string | null
export type Description = string
export type Dialect = string | null
export type DisplayName = string | null
export type Id = string
export type Name1 = string
export type QuerySql = string | null
export type SchemaName = string | null
export type SnapshotDateColumn = string | null
export type SourceKind = 'table' | 'query'
export type TableName = string | null
export type Datasets = Dataset[]
export type DataJoin = (DirectJoin | MappingTableJoin) | null
export type Kind = 'direct'
/**
 * @minItems 1
 * @maxItems 16
 */
export type SourcePropertyIds = [string, ...string[]]
/**
 * @minItems 1
 * @maxItems 16
 */
export type TargetPropertyIds = [string, ...string[]]
export type DatasetId = string
export type Kind1 = 'mapping_table'
/**
 * @minItems 1
 * @maxItems 16
 */
export type SourceColumns = [string, ...string[]]
export type SourceKey = MappingKey | PropertiesKey
export type Kind2 = 'mapping_key'
export type Kind3 = 'properties'
/**
 * @minItems 1
 * @maxItems 16
 */
export type PropertyIds = [string, ...string[]]
/**
 * @minItems 1
 * @maxItems 16
 */
export type TargetColumns = [string, ...string[]]
export type TargetKey = MappingKey | PropertiesKey
export type Description1 = string
export type DisplayName1 = string | null
export type Id1 = string
export type Kind4 = 'material'
export type Heading = string | null
export type LineEnd = number
export type LineStart = number
export type MaterialId = string
export type MaterialSha256 = string
export type Quote = string
export type CreatedAt = string
export type CreatedBy = string
export type Id2 = string
export type Kind5 = 'manual'
export type Note = string
/**
 * @maxItems 50
 */
export type Evidence = (MaterialEvidence | ManualEvidence)[]
export type Id3 = string
/**
 * No one_to_many: a one-to-many link is built from the many side.
 */
export type Multiplicity = 'one_to_one' | 'many_to_one' | 'many_to_many'
export type Name2 = string
export type SourceRoleName = string | null
export type SourceTypeId = string
/**
 * @maxItems 50
 */
export type Synonyms = string[]
/**
 * @maxItems 50
 */
export type Tags = string[]
export type TargetRoleName = string | null
export type TargetTypeId = string
/**
 * @maxItems 50
 */
export type Verbalizes = string[]
export type LinkTypes = LinkType[]
export type BindingMode = 'independent' | 'shared_parent'
export type Column = string
export type Kind6 = 'column'
export type SourceId = string
export type Expression = string
export type Kind7 = 'expression'
export type Id4 = string
export type MembershipSourceId = string | null
export type DatasetId1 = string
export type Id5 = string
/**
 * @maxItems 16
 */
export type KeyColumns = string[]
/**
 * @maxItems 64
 */
export type Sources = MappingSource[]
export type TypeId = string
export type Mappings = DataMapping[]
/**
 * @maxItems 50
 */
export type Evidence1 = (MaterialEvidence | ManualEvidence)[]
export type Id6 = string
export type SourceId1 = string
export type TargetId = string
export type TypeId1 = string
export type MaterialLinks = MaterialLink[]
/**
 * @maxItems 50
 */
export type Evidence2 = (MaterialEvidence | ManualEvidence)[]
export type Id7 = string
export type TypeId2 = string
export type MaterialObjects = MaterialObject[]
export type Aggregation = 'sum' | 'avg' | 'median' | 'min' | 'max' | 'count' | 'count_distinct'
export type DatasetId2 = string
export type Description2 = string
export type DisplayName2 = string | null
/**
 * @maxItems 50
 */
export type Evidence3 = (MaterialEvidence | ManualEvidence)[]
export type Column1 = string
export type DatasetId3 = string
export type Operator = 'eq' | 'ne' | 'gt' | 'ge' | 'lt' | 'le' | 'in' | 'not_in' | 'between' | 'is_null' | 'not_null'
/**
 * @maxItems 200
 */
export type Values1 = (string | number | boolean | null)[]
/**
 * @maxItems 50
 */
export type Filters = Condition[]
export type Id8 = string
export type Kind8 = 'simple'
export type Name3 = string
/**
 * @maxItems 50
 */
export type Synonyms1 = string[]
export type DenominatorId = string
export type Description3 = string
export type DisplayName3 = string | null
/**
 * @maxItems 50
 */
export type Evidence4 = (MaterialEvidence | ManualEvidence)[]
export type Id9 = string
export type Kind9 = 'ratio'
export type Name4 = string
export type NumeratorId = string
/**
 * @maxItems 50
 */
export type Synonyms2 = string[]
export type DatasetId4 = string
export type Description4 = string
export type DisplayName4 = string | null
/**
 * @maxItems 50
 */
export type Evidence5 = (MaterialEvidence | ManualEvidence)[]
export type Expression1 = string
export type Id10 = string
export type Kind10 = 'expression'
export type Name5 = string
/**
 * @maxItems 50
 */
export type Synonyms3 = string[]
/**
 * Ossie's seven built-in value types; core-1 adds no others.
 */
export type ValueKind = 'string' | 'integer' | 'decimal' | 'float' | 'boolean' | 'date' | 'datetime'
export type Metrics = (SimpleMetric | RatioMetric | ExpressionMetric)[]
/**
 * @minItems 1
 * @maxItems 50
 */
export type Conditions = [PathCondition, ...PathCondition[]]
export type Direction = 'forward' | 'reverse'
export type LinkTypeId = string
/**
 * @maxItems 8
 */
export type Links = LinkStep[]
export type PropertyId = string
/**
 * @maxItems 200
 */
export type Values2 = (string | number | number | boolean | null)[]
export type Kind11 = 'simple'
export type Expression2 = string
export type Kind12 = 'expression'
/**
 * @maxItems 20
 */
export type DerivedBy = (DerivedSimple | DerivedExpression)[]
export type Description5 = string
export type DisplayName5 = string | null
/**
 * @maxItems 50
 */
export type Evidence6 = (MaterialEvidence | ManualEvidence)[]
export type Extends = string | null
export type Id11 = string
export type Name6 = string
/**
 * @maxItems 50
 */
export type Synonyms4 = string[]
/**
 * @maxItems 50
 */
export type Tags1 = string[]
export type TitlePropertyId = string | null
export type ObjectTypes = ObjectType[]
export type Description6 = string
export type DisplayName6 = string | null
/**
 * @maxItems 50
 */
export type Evidence7 = (MaterialEvidence | ManualEvidence)[]
export type Id12 = string
export type Identifier = boolean
export type Name7 = string
export type OwnerTypeId = string
export type Required = boolean
/**
 * @maxItems 50
 */
export type Synonyms5 = string[]
export type Unique = boolean
export type ValueTypeId = string | null
export type Properties = Property[]
export type Description7 = string
export type DisplayName7 = string | null
/**
 * @maxItems 50
 */
export type Evidence8 = (MaterialEvidence | ManualEvidence)[]
export type Expression3 = string
export type Id13 = string
export type Name8 = string
export type OwnerId = string
export type RuleOwnerKind = 'object_type' | 'property' | 'link_type' | 'value_type'
export type RuleKind = 'constraint' | 'derivation'
export type Rules = Rule[]
export type SchemaVersion = 'core-1'
export type Description8 = string
export type DisplayName8 = string | null
/**
 * @maxItems 50
 */
export type Evidence9 = (MaterialEvidence | ManualEvidence)[]
export type Id14 = string
export type Name9 = string
export type ValueTypes = ValueType[]
export type WorkspaceId = string

export interface CoreDraft {
  datasets?: Datasets
  link_types?: LinkTypes
  mappings?: Mappings
  material_links?: MaterialLinks
  material_objects?: MaterialObjects
  metrics?: Metrics
  object_types?: ObjectTypes
  properties?: Properties
  rules?: Rules
  schema_version?: SchemaVersion
  value_types?: ValueTypes
  workspace_id: WorkspaceId
}
export interface Dataset {
  columns?: Columns
  connection_id?: ConnectionId
  description?: Description
  dialect?: Dialect
  display_name?: DisplayName
  id: Id
  name: Name1
  query_sql?: QuerySql
  schema_name?: SchemaName
  snapshot_date_column?: SnapshotDateColumn
  source_kind?: SourceKind
  table_name?: TableName
}
export interface DatasetColumn {
  comment?: Comment
  name: Name
  physical_type?: PhysicalType
}
export interface LinkType {
  data_join?: DataJoin
  description?: Description1
  display_name?: DisplayName1
  evidence?: Evidence
  id: Id3
  multiplicity: Multiplicity
  name: Name2
  source_role_name?: SourceRoleName
  source_type_id: SourceTypeId
  synonyms?: Synonyms
  tags?: Tags
  target_role_name?: TargetRoleName
  target_type_id: TargetTypeId
  verbalizes?: Verbalizes
}
/**
 * Source properties equal target properties, pair by pair.
 */
export interface DirectJoin {
  kind: Kind
  source_property_ids: SourcePropertyIds
  target_property_ids: TargetPropertyIds
}
export interface MappingTableJoin {
  dataset_id: DatasetId
  kind: Kind1
  source_columns: SourceColumns
  source_key: SourceKey
  target_columns: TargetColumns
  target_key: TargetKey
}
/**
 * The end object's main source `key_columns`.
 */
export interface MappingKey {
  kind: Kind2
}
/**
 * A single unique property or the end object's complete identifier.
 */
export interface PropertiesKey {
  kind: Kind3
  property_ids: PropertyIds
}
export interface MaterialEvidence {
  id: Id1
  kind?: Kind4
  locator: EvidenceLocator
  material_id: MaterialId
  material_sha256: MaterialSha256
  quote?: Quote
}
export interface EvidenceLocator {
  heading?: Heading
  line_end: LineEnd
  line_start: LineStart
}
/**
 * A member vouching for a fact. Author and time are written by the server.
 */
export interface ManualEvidence {
  created_at: CreatedAt
  created_by: CreatedBy
  id: Id2
  kind?: Kind5
  note?: Note
}
export interface DataMapping {
  binding_mode: BindingMode
  fields?: Fields
  id: Id4
  inherited_link_bindings?: InheritedLinkBindings
  membership_source_id?: MembershipSourceId
  sources?: Sources
  type_id: TypeId
}
export interface Fields {
  [k: string]: ColumnBinding | ExpressionBinding
}
export interface ColumnBinding {
  column: Column
  kind: Kind6
  source_id: SourceId
}
/**
 * A same-row expression over this object's own sources (`source.column`).
 */
export interface ExpressionBinding {
  expression: Expression
  kind: Kind7
}
export interface InheritedLinkBindings {
  [k: string]: DirectJoin | MappingTableJoin
}
export interface MappingSource {
  dataset_id: DatasetId1
  id: Id5
  key_columns?: KeyColumns
}
export interface MaterialLink {
  evidence?: Evidence1
  id: Id6
  source_id: SourceId1
  target_id: TargetId
  type_id: TypeId1
}
/**
 * A document fact. Its display text is derived on read, not stored.
 */
export interface MaterialObject {
  evidence?: Evidence2
  id: Id7
  type_id: TypeId2
  values?: Values
}
export interface Values {
  [k: string]: string | number | boolean | null
}
/**
 * value_kind is derived on read and not accepted as input.
 */
export interface SimpleMetric {
  aggregation: Aggregation
  dataset_id: DatasetId2
  description?: Description2
  display_name?: DisplayName2
  evidence?: Evidence3
  filters?: Filters
  id: Id8
  kind: Kind8
  measure?: ColumnReference | null
  name: Name3
  synonyms?: Synonyms1
  time_field?: ColumnReference | null
}
export interface Condition {
  column: ColumnReference
  operator: Operator
  values?: Values1
}
export interface ColumnReference {
  column: Column1
  dataset_id: DatasetId3
}
/**
 * dataset_id, time_field and value_kind come from the two components.
 */
export interface RatioMetric {
  denominator_id: DenominatorId
  description?: Description3
  display_name?: DisplayName3
  evidence?: Evidence4
  id: Id9
  kind: Kind9
  name: Name4
  numerator_id: NumeratorId
  synonyms?: Synonyms2
}
export interface ExpressionMetric {
  dataset_id: DatasetId4
  description?: Description4
  display_name?: DisplayName4
  evidence?: Evidence5
  expression: Expression1
  id: Id10
  kind: Kind10
  name: Name5
  synonyms?: Synonyms3
  time_field?: ColumnReference | null
  value_kind?: ValueKind | null
}
export interface ObjectType {
  derived_by?: DerivedBy
  description?: Description5
  display_name?: DisplayName5
  evidence?: Evidence6
  extends?: Extends
  id: Id11
  name: Name6
  synonyms?: Synonyms4
  tags?: Tags1
  title_property_id?: TitlePropertyId
}
/**
 * One membership branch: every condition must hold (AND).
 */
export interface DerivedSimple {
  conditions: Conditions
  kind: Kind11
}
export interface PathCondition {
  operator: Operator
  path: Path
  values?: Values2
}
/**
 * From a context object, through links, to one property. Ontology rules and
 * membership conditions only; metrics never use paths.
 */
export interface Path {
  links?: Links
  property_id: PropertyId
}
export interface LinkStep {
  direction: Direction
  link_type_id: LinkTypeId
}
export interface DerivedExpression {
  expression: Expression2
  kind: Kind12
}
export interface Property {
  description?: Description6
  display_name?: DisplayName6
  evidence?: Evidence7
  id: Id12
  identifier?: Identifier
  name: Name7
  owner_type_id: OwnerTypeId
  required?: Required
  synonyms?: Synonyms5
  unique?: Unique
  value_kind: ValueKind
  value_type_id?: ValueTypeId
}
export interface Rule {
  description?: Description7
  display_name?: DisplayName7
  evidence?: Evidence8
  expression: Expression3
  id: Id13
  name: Name8
  owner_id: OwnerId
  owner_kind: RuleOwnerKind
  rule_kind: RuleKind
}
/**
 * A named value domain shared by properties: base kind plus owned constraint rules.
 */
export interface ValueType {
  description?: Description8
  display_name?: DisplayName8
  evidence?: Evidence9
  id: Id14
  name: Name9
  value_kind: ValueKind
}
