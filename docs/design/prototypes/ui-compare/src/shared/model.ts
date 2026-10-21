// Shared fictional data and form logic for the three component-library prototypes.
// Every version renders the same state and calls the same functions, so only the
// component library and styling differ.

export type ColumnType = "string" | "integer" | "decimal" | "date";

export interface Column {
  name: string;
  type: ColumnType;
  comment: string;
}

export interface Dataset {
  id: string;
  name: string;
  table: string;
  rowMeaning: string;
  snapshotColumn?: string;
  /** false: no registered connection resolves this dataset. */
  connected?: boolean;
  /** false: the viewer may not read mappings, so SQL and preview are withheld. */
  readable?: boolean;
  columns: Column[];
  rows: Record<string, string | number | null>[];
}

export const DATASETS: Dataset[] = [
  {
    id: "orders",
    name: "订单",
    table: "sales.orders",
    rowMeaning: "一行 = 一张订单",
    columns: [
      { name: "order_id", type: "string", comment: "订单号" },
      { name: "customer_id", type: "string", comment: "客户编号" },
      { name: "status", type: "string", comment: "订单状态" },
      { name: "amount", type: "decimal", comment: "订单金额（元）" },
      { name: "order_date", type: "date", comment: "下单日期" },
      { name: "paid_date", type: "date", comment: "支付日期" },
    ],
    rows: [
      { order_id: "O-1001", customer_id: "C-01", status: "已完成", amount: 120, order_date: "2026-07-03", paid_date: "2026-07-03" },
      { order_id: "O-1002", customer_id: "C-02", status: "已完成", amount: 80, order_date: "2026-07-18", paid_date: "2026-07-19" },
      { order_id: "O-1003", customer_id: "C-01", status: "已取消", amount: 45, order_date: "2026-08-02", paid_date: null },
      { order_id: "O-1004", customer_id: "C-03", status: "已完成", amount: 210, order_date: "2026-08-21", paid_date: "2026-08-22" },
      { order_id: "O-1005", customer_id: "C-02", status: "已发货", amount: 66, order_date: "2026-09-05", paid_date: "2026-09-05" },
      { order_id: "O-1006", customer_id: "C-04", status: "已完成", amount: 150, order_date: "2026-09-28", paid_date: "2026-09-29" },
    ],
  },
  {
    id: "code_lines_daily",
    name: "代码行日统计",
    table: "dev.code_lines_daily",
    rowMeaning: "一行 = 一个代码仓库一天的统计",
    columns: [
      { name: "repo", type: "string", comment: "仓库" },
      { name: "stat_date", type: "date", comment: "统计日期" },
      { name: "commit_count", type: "integer", comment: "提交数" },
      { name: "added_lines", type: "integer", comment: "新增行数" },
    ],
    rows: [
      { repo: "core", stat_date: "2026-07-01", commit_count: 3, added_lines: 210 },
      { repo: "core", stat_date: "2026-08-02", commit_count: 5, added_lines: 340 },
      { repo: "web", stat_date: "2026-08-02", commit_count: 2, added_lines: 95 },
      { repo: "web", stat_date: "2026-09-10", commit_count: 4, added_lines: 180 },
    ],
  },
  {
    id: "inventory_daily",
    name: "库存每日快照",
    table: "wms.inventory_daily_df",
    rowMeaning: "一行 = 一个商品在某一天的库存",
    snapshotColumn: "snapshot_date",
    columns: [
      { name: "sku", type: "string", comment: "商品编码" },
      { name: "snapshot_date", type: "date", comment: "快照日期" },
      { name: "stock_qty", type: "integer", comment: "库存数量" },
    ],
    rows: [
      { sku: "A", snapshot_date: "2026-08-31", stock_qty: 10 },
      { sku: "B", snapshot_date: "2026-08-31", stock_qty: 4 },
      { sku: "A", snapshot_date: "2026-09-30", stock_qty: 8 },
      { sku: "B", snapshot_date: "2026-09-30", stock_qty: 6 },
    ],
  },
  {
    id: "stores",
    name: "门店维表",
    table: "retail.stores",
    rowMeaning: "一行 = 一家门店",
    columns: [
      { name: "store_id", type: "string", comment: "门店编号" },
      { name: "city", type: "string", comment: "城市" },
      { name: "area_sqm", type: "decimal", comment: "面积（平方米）" },
    ],
    rows: [
      { store_id: "S1", city: "上海", area_sqm: 120 },
      { store_id: "S2", city: "杭州", area_sqm: 86 },
    ],
  },
  {
    id: "finance_journal",
    name: "财务流水",
    table: "fin.journal",
    rowMeaning: "一行 = 一笔记账",
    connected: false,
    columns: [
      { name: "entry_id", type: "string", comment: "凭证号" },
      { name: "amount", type: "decimal", comment: "金额" },
      { name: "entry_date", type: "date", comment: "记账日期" },
    ],
    rows: [],
  },
  {
    id: "payroll",
    name: "薪资明细",
    table: "hr.payroll",
    rowMeaning: "一行 = 一个员工一个月的薪资",
    readable: false,
    columns: [
      { name: "employee_id", type: "string", comment: "员工编号" },
      { name: "pay_month", type: "date", comment: "发薪月份" },
      { name: "gross_pay", type: "decimal", comment: "应发工资" },
    ],
    rows: [],
  },
];

export type Kind = "count" | "sum" | "avg" | "max" | "min" | "count_distinct" | "median" | "ratio" | "expression";

export const KINDS: { id: Kind; label: string }[] = [
  { id: "count", label: "计数" },
  { id: "sum", label: "求和" },
  { id: "avg", label: "平均" },
  { id: "max", label: "最大" },
  { id: "min", label: "最小" },
  { id: "count_distinct", label: "去重计数" },
  { id: "median", label: "中位数" },
  { id: "ratio", label: "比率" },
  { id: "expression", label: "写表达式" },
];

export type Operator = "eq" | "neq" | "in" | "gt" | "gte" | "lt" | "lte" | "between" | "is_null" | "not_null";

export const OPERATORS: { id: Operator; label: string }[] = [
  { id: "eq", label: "等于" },
  { id: "neq", label: "不等于" },
  { id: "in", label: "属于" },
  { id: "gt", label: "大于" },
  { id: "gte", label: "大于等于" },
  { id: "lt", label: "小于" },
  { id: "lte", label: "小于等于" },
  { id: "between", label: "介于" },
  { id: "is_null", label: "为空" },
  { id: "not_null", label: "不为空" },
];

export interface Condition {
  id: string;
  column: string;
  operator: Operator;
  value: string;
}

export interface SavedMetric {
  id: string;
  name: string;
  datasetId: string;
  kind: Kind;
  column?: string;
  timeField?: string;
  description: string;
}

export const SAVED_METRICS: SavedMetric[] = [
  { id: "m1", name: "订单金额", datasetId: "orders", kind: "sum", column: "amount", timeField: "order_date", description: "全部订单的金额合计" },
  { id: "m2", name: "订单数", datasetId: "orders", kind: "count", timeField: "order_date", description: "订单行数" },
  { id: "m3", name: "已完成订单数", datasetId: "orders", kind: "count", timeField: "order_date", description: "状态为已完成的订单数" },
  { id: "m4", name: "提交数", datasetId: "code_lines_daily", kind: "sum", column: "commit_count", timeField: "stat_date", description: "代码提交次数合计" },
  { id: "m5", name: "期末库存", datasetId: "inventory_daily", kind: "sum", column: "stock_qty", timeField: "snapshot_date", description: "每个周期最后一天的库存合计" },
];

export interface FormState {
  name: string;
  synonyms: string[];
  datasetId: string | null;
  kind: Kind;
  column: string | null;
  conditions: Condition[];
  timeField: string | null;
  numeratorId: string | null;
  denominatorId: string | null;
  expression: string;
  description: string;
}

export const emptyForm = (): FormState => ({
  name: "",
  synonyms: [],
  datasetId: "orders",
  kind: "sum",
  column: "amount",
  conditions: [{ id: "c1", column: "status", operator: "eq", value: "已完成" }],
  timeField: "order_date",
  numeratorId: null,
  denominatorId: null,
  expression: "",
  description: "",
});

export const datasetOf = (id: string | null) => DATASETS.find((d) => d.id === id) ?? null;

export const NUMERIC: ColumnType[] = ["integer", "decimal"];

/** Columns the chosen calculation may aggregate. */
export function measureColumns(ds: Dataset | null, kind: Kind): Column[] {
  if (!ds) return [];
  if (kind === "sum" || kind === "avg" || kind === "median") return ds.columns.filter((c) => NUMERIC.includes(c.type));
  if (kind === "max" || kind === "min" || kind === "count_distinct") return ds.columns;
  return [];
}

export const dateColumns = (ds: Dataset | null) => (ds ? ds.columns.filter((c) => c.type === "date") : []);

export const simpleMetricsOn = (datasetId: string | null) =>
  SAVED_METRICS.filter((m) => m.datasetId === datasetId && m.kind !== "ratio" && m.kind !== "expression");

const SQL_AGG: Record<string, string> = {
  sum: "SUM", avg: "AVG", max: "MAX", min: "MIN", median: "MEDIAN", count_distinct: "COUNT(DISTINCT",
};

function conditionSql(c: Condition): string {
  const v = c.value.trim();
  const lit = (x: string) => (/^-?\d+(\.\d+)?$/.test(x) ? x : `'${x.replace(/'/g, "''")}'`);
  switch (c.operator) {
    case "eq": return `${c.column} = ${lit(v)}`;
    case "neq": return `${c.column} <> ${lit(v)}`;
    case "gt": return `${c.column} > ${lit(v)}`;
    case "gte": return `${c.column} >= ${lit(v)}`;
    case "lt": return `${c.column} < ${lit(v)}`;
    case "lte": return `${c.column} <= ${lit(v)}`;
    case "in": return `${c.column} IN (${v.split(/[,，]/).map((x) => lit(x.trim())).join(", ")})`;
    case "between": {
      const [a, b] = v.split(/[,，~]/).map((x) => x.trim());
      return `${c.column} BETWEEN ${lit(a ?? "")} AND ${lit(b ?? "")}`;
    }
    case "is_null": return `${c.column} IS NULL`;
    case "not_null": return `${c.column} IS NOT NULL`;
  }
}

/** Reference SQL for the current form, or the reason no SQL can be shown. */
export function referenceSql(f: FormState): { sql: string } | { reason: string } {
  const ds = datasetOf(f.datasetId);
  if (!ds) return { reason: "请先选择数据集" };
  if (ds.readable === false) return { reason: "你没有该数据集的映射读取权限，不显示 SQL 参考" };
  const where = f.conditions.filter((c) => c.column).map(conditionSql);
  if (ds.snapshotColumn && f.timeField !== ds.snapshotColumn) {
    where.push(`${ds.snapshotColumn} = (SELECT MAX(${ds.snapshotColumn}) FROM ${ds.table})`);
  }
  const whereSql = where.length ? `\nWHERE ${where.join("\n  AND ")}` : "";
  if (f.kind === "ratio") {
    const n = SAVED_METRICS.find((m) => m.id === f.numeratorId);
    const d = SAVED_METRICS.find((m) => m.id === f.denominatorId);
    if (!n || !d) return { reason: "请选择分子和分母指标" };
    return { sql: `-- 比率：${n.name} ÷ ${d.name}，分母为 0 时结果为空\nSELECT (${n.name}) / NULLIF((${d.name}), 0)` };
  }
  if (f.kind === "expression") {
    if (!f.expression.trim()) return { reason: "请填写表达式" };
    return { sql: `SELECT ${f.expression.trim()}\nFROM ${ds.table}${whereSql}` };
  }
  if (f.kind === "count") return { sql: `SELECT COUNT(*)\nFROM ${ds.table}${whereSql}` };
  if (!f.column) return { reason: "请选择要计算的列" };
  const agg = SQL_AGG[f.kind];
  const expr = f.kind === "count_distinct" ? `${agg} ${f.column})` : `${agg}(${f.column})`;
  return { sql: `SELECT ${expr}\nFROM ${ds.table}${whereSql}` };
}

function matches(row: Record<string, string | number | null>, c: Condition): boolean {
  const cell = row[c.column];
  const v = c.value.trim();
  const num = (x: unknown) => (typeof x === "number" ? x : Number(x));
  switch (c.operator) {
    case "eq": return String(cell) === v;
    case "neq": return String(cell) !== v;
    case "in": return v.split(/[,，]/).map((x) => x.trim()).includes(String(cell));
    case "gt": return num(cell) > num(v);
    case "gte": return num(cell) >= num(v);
    case "lt": return num(cell) < num(v);
    case "lte": return num(cell) <= num(v);
    case "between": {
      const [a, b] = v.split(/[,，~]/).map((x) => x.trim());
      return String(cell) >= (a ?? "") && String(cell) <= (b ?? "");
    }
    case "is_null": return cell == null;
    case "not_null": return cell != null;
  }
}

function aggregate(kind: Kind, values: (string | number | null)[], rowCount: number): number | null {
  const nums = values.filter((v): v is number => typeof v === "number");
  switch (kind) {
    case "count": return rowCount;
    case "sum": return nums.reduce((a, b) => a + b, 0);
    case "avg": return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
    case "max": return nums.length ? Math.max(...nums) : null;
    case "min": return nums.length ? Math.min(...nums) : null;
    case "count_distinct": return new Set(values.filter((v) => v != null)).size;
    case "median": {
      if (!nums.length) return null;
      const s = [...nums].sort((a, b) => a - b);
      const m = Math.floor(s.length / 2);
      return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    }
    default: return null;
  }
}

export interface Preview {
  ok: boolean;
  reason?: string;
  total?: number | null;
  trend?: { month: string; value: number | null }[];
}

/** Stand-in for the platform's read-only preview run against the dataset. */
export function preview(f: FormState): Preview {
  const ds = datasetOf(f.datasetId);
  if (!ds) return { ok: false, reason: "请先选择数据集" };
  if (ds.readable === false) return { ok: false, reason: "你没有该数据集的映射读取权限" };
  if (ds.connected === false) return { ok: false, reason: `数据集 ${ds.table} 没有可用的已登记连接` };
  if (f.kind === "ratio" || f.kind === "expression") {
    return { ok: false, reason: f.kind === "ratio" ? "原型未模拟比率预览" : "表达式预览需要后端编译，原型中显示为无法预览" };
  }
  if (f.kind !== "count" && !f.column) return { ok: false, reason: "请选择要计算的列" };
  let rows = ds.rows.filter((r) => f.conditions.every((c) => !c.column || matches(r, c)));
  const snap = ds.snapshotColumn;
  const valueOf = (rs: typeof rows) => aggregate(f.kind, rs.map((r) => (f.column ? r[f.column] : 1)), rs.length);
  if (snap && f.timeField !== snap) {
    const last = rows.map((r) => String(r[snap])).sort().at(-1);
    rows = rows.filter((r) => String(r[snap]) === last);
  }
  let total: number | null;
  if (snap && f.timeField === snap) {
    const last = rows.map((r) => String(r[snap])).sort().at(-1);
    total = valueOf(rows.filter((r) => String(r[snap]) === last));
  } else {
    total = valueOf(rows);
  }
  let trend: Preview["trend"];
  if (f.timeField) {
    const tf = f.timeField;
    const months = [...new Set(rows.map((r) => String(r[tf] ?? "").slice(0, 7)).filter(Boolean))].sort();
    trend = months.map((month) => {
      let inMonth = rows.filter((r) => String(r[tf] ?? "").startsWith(month));
      if (snap && tf === snap) {
        const last = inMonth.map((r) => String(r[snap])).sort().at(-1);
        inMonth = inMonth.filter((r) => String(r[snap]) === last);
      }
      return { month, value: valueOf(inMonth) };
    });
  }
  return { ok: true, total, trend };
}

export function formatNumber(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number.isInteger(v) ? v.toLocaleString("zh-CN") : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export const kindLabel = (k: Kind) => KINDS.find((x) => x.id === k)?.label ?? k;

let seq = 10;
export const newConditionId = () => `c${++seq}`;
