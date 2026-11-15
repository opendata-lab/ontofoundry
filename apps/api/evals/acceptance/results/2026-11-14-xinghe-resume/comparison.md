# 星河零售回归完成

已接受全部提案并发布 v1、v2。数值顺序为本次／clean／rerun，抽取包含网络恢复。

| 指标 | 计划 | 全量抽取 | 全量合计 | 增量 |
|---|---:|---:|---:|---:|
| 轮数 | 10／9／8 | 21／31／22 | 31／40／30 | 9／11／10 |
| 工具调用 | 13／10／10 | 25／34／26 | 38／44／36 | 11／13／10 |
| 工具输出 B | 7,124／7,629／8,542 | 34,638／25,600／24,403 | 41,762／33,229／32,945 | 11,644／15,642／19,501 |
| 平台提交 | — | — | 1／4／2 | 1／1／1 |
| repair_used/limit | — | — | 0/3／3/3／1/3 | 0/3／0/3／0/3 |
| 提案 | — | — | 64／64／63 | 7／8／8 |
| 费用 ¥ | — | — | 0.05／0.15／0.04 | 0.06／0.09／0.21 |

余额 ¥8.43→8.38→8.32，合计 ¥0.11（clean ¥0.24，rerun ¥0.25）。B 沿用指定 tool_stats.py 的字符串长度口径，归档已脱敏。各类调用及每步差值见 results 各目录 summary.json、tool-stats.txt。

## 工具调用检查

- 全量各用一次 `show_example.py --extract 1`、`--extract 2`，额外一次 `--help`，单独 `--guide/--values/--part` 均为 0。
- 全量 check_part 共 4 次，含 1 次 help、2 次片段检查、1 次恢复检查。增量 1 次，`--incremental-guide` 恰好 1 次。
- notes.md 全量、增量各写一次，未修剪。各轮均未读取自动生成的需求材料文件。
- 网络恢复仅 4 轮、3 调用，沿用 64 条原片段，写入和编辑调用均为 0。

## Findings

- 全量对调整后的夹具 62 条，多 1 个 value_type、1 条 rule。实际 object_type/property/value_type/link_type/dataset/mapping/metric/rule 为 6/30/3/6/5/5/3/6。增量 dataset/mapping/metric 为 2/1/4，与 7 条夹具一致，refunds 为新增。类型数量比较已归档，完整语义等价未评审。
- 两次平台实际接收均通过，校验错误为 0。全量另有 2 次网络未送达，均报 `PLATFORM_SUBMIT_UNAVAILABLE`、`Temporary failure in name resolution`。
- 本次走 API 默认权限模式。Agent 先以文本计划结束，平台显示“本轮没有提交通过检查的结果”，result_state 为 failed_permanent。发送规定改名回复后继续。空本体查询另返回一次包含六个 `TARGET_NOT_FOUND` 的结果。
- 原 API/web 均停用。本次临时 API 已停止，原验收 PostgreSQL/MySQL 已恢复，临时沙箱配置已撤销，8902 保持运行。仓库 clean，未修改代码、commit、push，未跑测试套件、问数或 OpenDataWorks。

## Problems

隔离沙箱网络初始关闭。临时启用并重启 8902，连通性验证后增加一条“平台连接已恢复，请沿用已有成果完成平台提交。”完成恢复，统计包含该开销，因此全量性能比较受环境影响。未发生模型流中断。

准备时旧环境含已移除的 OAuth 配置，筛除临时进程中的旧键后 Alembic 成功。首次同步漏传 schema 返回 `SCHEMA_REQUIRED`，按接口补齐后成功。一次连通性探测误用了不存在的镜像标签，随后读取容器配置，使用已有镜像验证 HTTP 200。上述失败均已恢复。
