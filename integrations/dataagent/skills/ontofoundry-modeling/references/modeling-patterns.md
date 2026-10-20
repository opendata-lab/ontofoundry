# 建模模式

虚构的星港销售空间：订单、客户分对象；订单的客户编号是属性，订单属于客户另建关系。
纯配对表建 mapping_table 关系；带数量或成绩的配对建中间对象，再分别连接两端。
多方业务事实建中间对象，不在内部模型增加角色节点。
有序复合物理键与业务标识分开；不同子类型相同局部键不能合并。
无对象时也可登记 Dataset 和指标；例如提交行数、核心提交数及二者 ratio。
虚拟父只表达业务类别；具体绑定来源并集保留实际类型。父有绑定时，子类逐层声明成员范围。
SQL 写法、精度、时区、强制转换、空周期展示和执行性能交给查询 Agent，不加模型开关。


## 父绑定覆盖全部子实例

虚构“星港员工”的父映射主来源 fictional_staff 含员工编号 E01、E02、E03；“星港主管”继承员工，用 shared_parent 和 derived_by 筛出 E02。父来源必须已经覆盖 E02；子类可用扩展来源补充属性或通过 membership_source_id 取交集，不能把仅在扩展表中的 E04 添入父集合。若主管表还有 E04，应先补全父来源覆盖的业务范围，不能给有绑定父类的子类另设 independent。虚拟父没有绑定时，具体子类才可 independent，父读取时取具体子来源并集。

## 文档对象与关系事实的最小提案

以下是本轮 items 数组，完整结果头逐字使用本轮上下文。示例均为虚构；省略 evidence 表示没有材料证据，有材料时应填真实材料引用与行号。

```json
[
  {"operation":"create","target_kind":"object_type","client_ref":"staff","before":null,"after":{"name":"星港员工","technical_name":"starport_staff","title_property_id":{"client_ref":"staff_name"}}},
  {"operation":"create","target_kind":"property","client_ref":"staff_name","before":null,"after":{"owner_type_id":{"client_ref":"staff"},"name":"姓名","technical_name":"staff_name","value_kind":"string"}},
  {"operation":"create","target_kind":"link_type","client_ref":"reports","before":null,"after":{"name":"reports_to","source_type_id":{"client_ref":"staff"},"target_type_id":{"client_ref":"staff"},"multiplicity":"many_to_one","source_role_name":"下属","target_role_name":"主管","verbalizes":["{source}汇报给{target}","{target}管理{source}"]}},
  {"operation":"create","target_kind":"material_object","client_ref":"lan","before":null,"after":{"type_id":{"client_ref":"staff"},"values":{"staff_name":"小岚"}}},
  {"operation":"create","target_kind":"material_object","client_ref":"zhou","before":null,"after":{"type_id":{"client_ref":"staff"},"values":{"staff_name":"小舟"}}},
  {"operation":"create","target_kind":"material_link","client_ref":"lan_reports","before":null,"after":{"type_id":{"client_ref":"reports"},"source_id":{"client_ref":"lan"},"target_id":{"client_ref":"zhou"}}}
]
```

after 不含自身 id，服务端分配 UUID；values 键保持 staff_name，关系事实 type_id 引用关系类型，source_id/target_id 引用两端文档对象。文档对象不因同名或同编号自动合并。
