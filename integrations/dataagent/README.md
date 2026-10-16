# DataAgent core-1 发布操作

平台仅引用已有 DataAgent Agent；仓库编辑不会自动同步管理后台。
源码：`skills/ontofoundry-modeling/`；分发包由 `make -C integrations/dataagent zip` 生成，产物 `dist/ontofoundry-modeling.zip` 不提交。

以下只在完整 P2 前后端集成验收后由发布人员执行，不由自动测试启动或重启外部系统：

1. 正常运维备份平台数据库和磁盘材料；停止旧建模运行及结果同步，关闭切换窗口的新写入。
2. 删除运行时旧技能目录，将新 ZIP 解压到 `SKILLS_ROOT_DIR`（或复制源码目录）；不要并存旧目录。
3. 在 DataAgent 管理后台把已有建模 Agent 的技能配置改为 ontofoundry-modeling；同步并发布 [建模提示词](agents/agent_ontofoundry.md) 和 [问数提示词](agents/agent_ontofoundry_qa.md)。平台不创建或修改 Agent。
4. 重启 DataAgent 使其重新索引技能，检查 capabilities 能看到 ontofoundry-modeling。此操作不得放进自动测试。
5. 停止旧应用进程，确认备份后执行 Alembic 升级到 `20261016_000001`；清空旧提案、会话、身份和版本，不转换旧数据；保留用户、工作空间、成员、材料/分块、数据连接、服务令牌/范围、元数据快照及磁盘材料。
6. 同时部署 core-1 前后端，重启应用以清除进程内 read_cache。旧 run grant 因会话删除立即失效，旧回调不能复活会话。服务令牌仍存在，但未发布空间返回空 MCP 目录。
7. 验证从空空间建模、审阅、接受、预览、发布及四工具读取；验证问数通过 DataAgent 自有数据库工具聚合。导入/导出入口在 P4/P5 交付前保持下线。

迁移仅在部署窗口执行；回滚旧内容依赖备份，downgrade 不能恢复已清空的数据。
本工作树无 .env，不连接开发数据库。测试只用测试自建临时 SQLite 或显式 disposable PostgreSQL/MySQL。
