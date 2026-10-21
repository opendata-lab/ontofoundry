import { Descriptions, Segmented, Table, Typography } from "antd";
import { useState } from "react";
import type { TranslationIssue, TranslationReportData } from "../api/types";
import { StatusMark } from "./layout";

const CONSTRUCTS: Record<string, string> = { object_types: "对象", properties: "属性", link_types: "关系", rules: "规则", metrics: "指标", datasets: "数据集", mappings: "映射", material_objects: "文档实例", material_links: "关系实例", ObjectType: "对象", Metric: "指标", Dataset: "数据集", DatasetMetadata: "数据集元数据", document: "整个文件", Document: "文件信息", InputItem: "来源定义", OntologyMap: "映射分组", ObjectMapping: "对象映射", RelationshipBinding: "关系绑定", material_evidence: "材料证据" };
export function TranslationReport({ report, idMap = {} }: { report: TranslationReportData; idMap?: Record<string, string> }) {
  const [filter, setFilter] = useState("all");
  const outcomes = { converted: "已转换", dropped: report.direction === "export" ? "未导出" : "未导入", error: "需处理" };
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <Segmented aria-label="转换结果筛选" value={filter} onChange={setFilter} options={[{ value: "all", label: `全部 ${report.issues.length}` }, ...Object.entries(outcomes).map(([value, label]) => ({ value, label: `${label} ${report.issues.filter((i) => i.outcome === value).length}` }))]} />
      <Table<TranslationIssue>
        size="small" rowKey="id" pagination={{ pageSize: 10, hideOnSinglePage: true }}
        dataSource={report.issues.filter((i) => filter === "all" || i.outcome === filter)}
        columns={[
          { title: "结果", key: "outcome", width: 100, render: (_, i) => <StatusMark state={i.outcome === "converted" ? "mapped" : i.outcome === "error" ? "error" : "partial"} label={outcomes[i.outcome]} /> },
          { title: "内容", key: "construct", width: 130, render: (_, issue) => <Typography.Text title={issue.construct}>{CONSTRUCTS[issue.construct] ?? "来源条目"}</Typography.Text> },
          { title: "说明", dataIndex: "message" },
        ]}
        expandable={{ expandedRowRender: (issue) => (
          <div className="flex min-w-0 flex-col gap-2">
            <Descriptions size="small" column={1} items={[
              { key: "path", label: report.direction === "export" ? "模型位置" : "文件位置", children: <Typography.Text code className="break-all">{issue.source_path || "整个文件"}</Typography.Text> },
              ...(report.direction === "export" ? [] : [{ key: "lines", label: "材料定位", children: issue.source_locator.line_start ? `格式化材料第 ${issue.source_locator.line_start}–${issue.source_locator.line_end} 行` : issue.source_locator.line ? `原始文件第 ${issue.source_locator.line} 行，第 ${issue.source_locator.column} 列` : "无可用行号" }]),
              { key: "rule", label: "转换规则", children: issue.rule_id ?? "—" },
              { key: "targets", label: "对应元素", children: issue.target_element_ids.length ? issue.target_element_ids.map((id) => <Typography.Paragraph key={id} copyable className="m-0 break-all">{idMap[id] ?? id}</Typography.Paragraph>) : "—" },
            ]} />
            {issue.original && <Typography.Paragraph className="m-0 max-h-review-code overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{issue.original}</Typography.Paragraph>}
          </div>
        ) }}
        locale={{ emptyText: "没有这类转换结果" }}
      />
    </div>
  );
}
