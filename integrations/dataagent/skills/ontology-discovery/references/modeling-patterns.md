# 复杂判断

## 继承覆盖

父表 E01/E02/E03，主管取 E02：shared_parent 沿父映射，用成员条件筛选；扩展来源只取交集，不把 E04 加入父成员。若主管含 E04，需补全父覆盖或确认虚拟父／独立对象。虚拟父合并具体子来源，相同局部键01仍保留不同具体类型身份。例见 [继承](examples/inheritance.json)、[虚拟父](examples/virtual-parent.json)、[成员](examples/membership.json)。

## 重化

纯配对可建 mapping_table 关系；有数量、成绩、日期或多方参与时，判断是否独立事件。客户01同日买同商品两次，按事件号保留2条，不用参与方组合压成1条。多方事件以中间对象分别连端点；外部 Ossie 元组按现有转换规则，不能混用事件键。例见 [重化事件](examples/reified-event.json)。

## 定点补读

[主管与协作关联](examples/link-joins.json)、[同行计算](examples/expression-binding.json)、[实例复用](examples/reuse-fact.json) 均按触发分支读取。仅改名称无需全读；字段写法通过 show_example，不在本文件复制 JSON。
