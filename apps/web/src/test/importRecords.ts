import type { ImportPreview } from "../api/types";
export const importPreview: ImportPreview = {
  import_id: "fiction-import", adapter: "ossie-0.2", filename: "fiction.json", content_sha256: "a".repeat(64), raw_sha256: "b".repeat(64), formatted_sha256: "c".repeat(64), material_id: "fiction-material", base_version_id: null,
  report: { id: "fiction-report", content_sha256: "d".repeat(64), direction: "import", adapter: "ossie-0.2", counts: { converted: 1, error: 1, dropped: 0 }, issues: [
    { id: "issue-converted", outcome: "converted", construct: "ObjectType", rule_id: "RT-01", severity: "info", source_path: "/ontology/0", source_locator: { json_pointer: "/ontology/0", line_start: 4, line_end: 12, formatted_sha256: "c".repeat(64) }, original: '{"concept":"fiction_order","type":"EntityType"}', target_element_ids: ["file-order"], completion_status: "not_needed", target_path: null, message: "保留业务对象定义" },
    { id: "issue-count", outcome: "error", construct: "Metric", rule_id: "RT-47", severity: "error", source_path: "/ontology_mappings/0/semantic_model/metrics/0", source_locator: { line_start: 15, line_end: 19 }, original: '{"name":"order_count","expression":"COUNT(*)"}', target_element_ids: [], completion_status: "available", target_path: null, message: "指标没有可确定的列来源，请选择数据集" },
  ] },
  proposal_summary: { create: 3, update: 1, unchanged: 2, blocked: [] }, id_map: { "file-order": "workspace-order" }, document_error: false, confirmed: null, current_blocked: [],
  completion: [{ issue_id: "issue-count", message: "指标没有可确定的列来源，请选择数据集", original: '{"name":"order_count","expression":"COUNT(*)"}', source_path: "/ontology_mappings/0/semantic_model/metrics/0", source_locator: { line_start: 15, line_end: 19 }, kind: "count_dataset", datasets: [{ id: "fiction-dataset", name: "虚构订单数据" }], status: "available" }],
};
