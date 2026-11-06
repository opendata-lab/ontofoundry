{
  "expected_total": 69,
  "actual_total": 71,
  "expected_counts": {
    "dataset": 7,
    "mapping": 6,
    "link_type": 6,
    "object_type": 6,
    "property": 30,
    "value_type": 2,
    "rule": 5,
    "metric": 7
  },
  "actual_counts": {
    "object_type": 6,
    "property": 30,
    "link_type": 6,
    "rule": 6,
    "metric": 7,
    "dataset": 7,
    "mapping": 6,
    "value_type": 3
  },
  "count_diffs": {
    "value_type": 1,
    "rule": 1
  },
  "query_datasets": [
    {
      "id": "369db78d-c2d9-5193-8d61-0ebb63cf2bd1",
      "name": "sales_refund_daily",
      "display_name": "销售与退款事件",
      "connection_id": "8ae267d6-5a24-4fba-9874-6bed466d024d",
      "source_kind": "query",
      "dialect": "mysql",
      "schema_name": null,
      "table_name": null,
      "query_sql": "SELECT o.order_date AS event_on, o.pay_amount AS sales_amount, 0 AS refund_amount FROM xinghe_retail.orders o WHERE o.status = '已完成' UNION ALL SELECT r.refund_date AS event_on, 0 AS sales_amount, r.refund_amount AS refund_amount FROM xinghe_retail.refunds r",
      "description": "销售额与退款金额各自保留业务日期（下单日期、退款日期）后合并为事件，供跨表比率指标使用；列声明来自已同步表结构，不声称 SQL 已探测执行",
      "snapshot_date_column": null,
      "columns": [
        {
          "name": "event_on",
          "physical_type": "date",
          "comment": ""
        },
        {
          "name": "sales_amount",
          "physical_type": "decimal",
          "comment": ""
        },
        {
          "name": "refund_amount",
          "physical_type": "decimal",
          "comment": ""
        }
      ]
    }
  ]
}