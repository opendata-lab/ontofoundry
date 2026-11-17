# 接受时检查：实施计划

设计见 [2026-11-15-accept-completeness.md](../design/2026-11-15-accept-completeness.md)。本计划覆盖 AC-01、02、04、05、08、09、10、11；AC-03、AC-12 已实施，AC-07 另起 PR，验证（第 10 节）在全部实施后进行。

## 后端

1. `domain/accept_checks.py`（新）：
   - `definition_issues(draft, items)`：本次接受影响的对象（对象、属性所属对象、映射对象、所用数据集的对象，及共享绑定的子对象）若已绑定表，检查逻辑键、每个有效属性有绑定、来源数据集列已同步（AC-04）；接受的指标所用数据集列未同步（AC-10）。
   - `link_count_issues(draft, objects, links, changed)`：本次接受的关系实例按声明基数检查（AC-11）。
2. `domain/instance_validation.py`：`strict` 时必填／标识缺值为错误（AC-02）。
3. `domain/validation.py`：约束规则和成员条件的根节点明显不是条件（算术、常量、文本拼接、非条件函数）时报错（AC-09）。这是定义本身错误，提交时即报，不等到接受。
4. `services/proposal_apply.py`：`trial_apply(..., accepting=True)` 调用上述检查（AC-01、AC-08：没有实例就不做实例检查）。
5. 批次读取：每个提案增加 `acceptance_issues`（字符串列表），用同一组函数按“全部待审提案都接受”的候选计算，不存储（AC-05）。

## 前端

6. `api/types.ts` 增加 `acceptance_issues`；`reviewMeta.acceptanceBlock` 把它当作不能接受的原因。
7. 提案卡片显示警示图标，悬停列出问题；状态标签增加“待补全 N”（AC-05）。按界面规范在 1440×900 截图对比，运行 `npm run test:visual`。

## 文档

8. 按设计第 7 节修改主设计、概念文档中与 AC-02、AC-04 冲突的表述（AC-07 相关表述随 AC-07 修改）。

## 测试

- 每条规则：拦截、消息、补全后通过；无关提案不被连带阻止；只接受定义时不查实例。
- 批次读取的 `acceptance_issues` 与接受时的拒绝一致。

## AC-07 已实施（2026-11-17，Claude）

- `domain/rule_evaluation.py`：只对允许清单求值（比较、IN、BETWEEN、AND/OR/NOT、Decimal 四则运算、LIKE/ILIKE、REGEXP_LIKE、LOWER/UPPER/TRIM/LENGTH）；数字与文本相比、除数为零、清单外函数（如 ROUND、COALESCE）一律“规则未检查”，不猜测。
- 接受文档实例时（`proposal_apply._instances`）求值：值类型约束（对使用它的每个属性）、只引用本对象属性的对象／属性约束；不满足则拒绝，消息为“客户「测试客户」：名称（label）为 '测试客户'，不满足规则 不收测试客户（no_test_customer）（表达式）”。关系上的规则、经关系跳转的规则提示“规则未检查：规则名，涉及其他对象”；派生规则和空值不求值。
- 提示放在决定响应的 `validation.warnings`（`code = RULE_NOT_CHECKED`），审阅面板的结果提示里显示，不改契约。
- 测试：`tests/test_rule_evaluation.py`（各写法、精确小数、清单外、跨对象、派生、空值）、`tests/test_rule_acceptance.py`（经接口拒绝与提示）、面板测试。
