# 青禾 Q3 质量核对

依据本工作树 qinghe-scale/README.md、material.md、最终 batch 与原始会话。仅核对定义，没有执行问数。

| 材料的 11 条指标口径 | 状态 | 最终表达及核对 |
|---|---|---|
| 销售额 | present | 已完成销售订单正事件，已退款单负事件，按下单/审核时间 |
| 订单数 | present | 订单事件 order_cnt=1、退款事件为 0，合计 |
| 客单价 | present | 销售额 / 订单数 |
| 毛利（含毛利率） | present | 正事件实付减明细成本，退款事件为负退款金额加退款明细成本，毛利率为毛利/销售额 |
| 会员销售占比 | present | member_id 非空的净销售额 / 全部净销售额 |
| 会员复购率 | present，口径错误 | member_order_daily 按会员×日 COUNT(*)；复购会员数先过滤每日 order_count>=2，再 COUNT DISTINCT member_id |
| 动销率 | present | 当前在售商品×有销售日，销售量>0的 SKU / 所有在售 SKU；历史在售状态不可追溯已解释 |
| 库存周转天数 | present | 快照覆盖日的库存成本均值 / 同日销售成本均值 |
| 盘亏损耗率 | present | 已确认盘点的正盘亏成本 / 已完成销售成本，UNION ALL 同源分量 |
| 准时送达率 | present | 已送达配送中 delivered_at<=promised_at 的数量 / 已送达数量 |
| 优惠券核销率 | present | 发放表 status=已使用 的行数 / 发放行数 |

present 11，explained 0，missing 0。25 个 metric 包含毛利率与支撑分量。原基线未交付 2 项，Q1/Q2 未交付 1 项。

会员复购反例由最终 SQL 和指标定义直接推导。一个会员在 1 月 1 日、1 月 2 日各完成一单，统计期为整个 1 月。两条每日汇总的 order_count 均为 1，复购分子筛选后为 0、下单会员数为 1，结果为 0%。材料要求统计期合计至少两单，预期为 100%。最终答复声称所有口径落地，没有解释这个偏差。

| 六条最低业务规则 | 分类 | 核对 |
|---|---|---|
| 只有已完成订单计入销售 | filter | 销售分支 WHERE o.status='已完成' |
| 退款审核通过才算完成 | rule + filter | refund.status<>'已退款' OR approved_at IS NOT NULL；退款分支 WHERE status='已退款' |
| 拒收不计库存 | explained，另有同名 rule | 说明写了不计库存，表达式仅 qty_rejected>=0，无法校验拒收是否入库 |
| 生鲜只能存冷链仓 | rule | inventory_snapshot.inventory_product.is_fresh=FALSE OR inventory_snapshot.inventory_warehouse.wh_type='冷链'；关系说明限定仓库行，表达式没有 location_type 条件 |
| 临期定义 | explained，另有折扣 rule | 剩余保质期不足三分之一仅在说明，表达式只校验 reason='临期' 时 new_price<old_price；Agent 明确解释未落地日期判定 |
| 闭店门店不计在营 | explained，另有同名 rule | 表达式 store.status='闭店' OR store.closed_on IS NULL，只校验状态/日期，不定义在营范围 |

规则总计 30 条，其中 24 条 owner_kind=value_type 的取值约束、6 条其他业务规则。后六条包含额外的正盘亏成本派生规则，不能据总数认定最低六条均完整实现。闭店且 closed_on 非空的行满足所谓闭店排除规则，拒收数量为 5 且已错误入库也满足拒收规则，均不能完成其名称声称的业务校验。

## 实体、排除表和关系

31 个对象覆盖参考按主单/明细展开的 30 个业务类型，另含日历日期。promotion_products 作为活动—商品多对多关联表，未单独建实体，理由已说明。ods_sync_log 与 tmp_sales_orders_bak_20250101 均排除。

库存快照→仓库、→门店及→商品关系均存在。前两条均以 location_id 直接连接，location_type 条件只在 description。商品品类自关联、员工所在门店/门店店长、采购/入库/调拨/盘点、会员/券/促销、支付/退款/配送等参考关系均有对应定义。

## 覆盖提醒和技能路径

entities.json 含 46 条 links。expand_tables 实际运行 3 次，首次 SPEC_INVALID（关系与对象同名），随后两次生成通过。02-links.json 由脚本生成，没有 02b。没有写 *.py 文件，使用了内联 Python 编辑 entities 和生成查询/指标片段。01b 无、03b 有，search/describe 为 0/5。

04 检查提醒材料 L3、L15 未被引用和会员价计划规则缺失。Agent 增加临期降价规则，并从 planned_rules 删掉会员价规则，最终说明缺少会员价适用标志及临期日期判定。覆盖提醒的消失包含计划修改。

## Problems

会员复购率漏跨日复购。拒收与闭店规则表达式未落实其业务名称。临期阈值仅说明。库存地点条件只写在关系说明。首次平台提交 ELEMENT_INVALID，修正关系路径后通过，repair_used=1/3。
