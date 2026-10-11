from ontofoundry_api.services.table_material import foreign_key_hints, tables_markdown


def column(name, type_="BIGINT", pk=False, nullable=False, comment=None):
    return {"name": name, "type": type_, "primary_key": pk, "nullable": nullable,
            "comment": comment}


CUSTOMERS = {
    "name": "customers", "comment": None, "row_count": 8,
    "columns": [column("id", pk=True), column("customer_name", "VARCHAR(128)")],
    "samples": [{"id": 1, "customer_name": "星海贸易"}, {"id": 2, "customer_name": "晨光零售"}],
}
ORDERS = {
    "name": "orders", "comment": "客户订单", "row_count": 780,
    "columns": [column("id", pk=True), column("customer_id"),
                column("total_amount", "DECIMAL(12, 2)", comment="订单 | 金额")],
    "samples": [{"id": 1, "customer_id": 1, "total_amount": 240}],
}


def test_foreign_keys_are_inferred_from_names_and_declared_constraints():
    hints = foreign_key_hints([CUSTOMERS, ORDERS])
    assert hints["orders"] == [("customer_id", "customers", "按命名推断")]
    declared = {**ORDERS, "foreign_keys": [{"column": "customer_id", "table": "customers"}]}
    assert foreign_key_hints([CUSTOMERS, declared])["orders"] == [
        ("customer_id", "customers", "外键约束")
    ]
    # A target outside the selection is not guessed.
    assert foreign_key_hints([ORDERS])["orders"] == []


def test_markdown_names_everything_a_mapping_proposal_needs():
    text = tables_markdown(source="销售业务库", kind="mysql", database="demo_analytics",
                           schema=None, tables=[CUSTOMERS, ORDERS])
    assert "数据源（connection_alias）：销售业务库" in text
    assert "模式（schema_name）：demo_analytics" in text
    assert "## 表 orders" in text and "- 主键（key_column）：id" in text
    assert "- orders.customer_id → customers.id（按命名推断）" in text
    assert "| customer_name | VARCHAR(128) | 否 |  |  | 星海贸易, 晨光零售 |" in text
    # Cell text cannot break the table.
    assert "订单 \\| 金额" in text
