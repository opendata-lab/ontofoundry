# 阅读 Ossie 外部材料

Ossie 是外部交换格式，不是内部提案形状。roles 和 owner_ref 表达外部关系角色；二元关系映射为核心两端，roles[0].name 保存到 target_role_name，隐式源端不猜测；source_role_name 可从已记录的平台扩展恢复。多元事实重化为普通中间对象，实体角色名保留到生成关系的 target_role_name。角色名称不替代关系读法，核心 name 是 ASCII 标识，verbalizes 完整保存正反向句式列表。内部模板使用 {source}/{target}，从外部 {概念}/{概念:角色} 按端点机械替换，不截取动词、尾部或其他读法。
外部 semantic_model/field 树要转换为扁平 Dataset、Mapping、Metric；不能照抄进核心草稿。
无法确定的业务关系、数据源、时间约定应保留原文并向用户说明，不猜测，也不声称无损。
不能把文件整体包在结果内，必须翻译成符合本轮 schema 的提案。

关系示例：name=reports_to，来源角色下属、目标角色主管，verbalizes=["{source}汇报给{target}", "{target}管理{source}"]。角色名可空，不从旧词语猜测；无读法时给空数组。每条读法必须包含两个端点，不使用未知占位符。
