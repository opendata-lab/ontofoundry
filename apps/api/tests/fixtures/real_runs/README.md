# 真实建模回放（M8）

`topdown-raw-result.json` 与 `topdown-replay.json` 从评审方指定的 scratchpad 文件逐字节复制，未改写提案、client_ref、角色顺序、运行头或证据。运行头中的 run_token 是回放关联标识，不是认证凭据。

原始结果为 26 条 proposals/v1 提案，其中 6 条二元 material_link 只提供 role_values。replay 文件包含运行固定的草稿、已发布版本的读取投影及原批次，草稿哈希与原运行头一致；已发布读取投影的当前哈希不能替代运行头中的历史版本哈希。

源材料全文未随回放提供。测试按提案内的多行/单行 quote 与原 locator 重建证据行，保留原材料 ID/声明的哈希元数据，使用实际 material_lookup 验证引用；不宣称重建了全文内容或重新校验全文 SHA。所有数据库和材料文件只放在测试临时目录/临时 PostgreSQL 库中，不操作实际业务库。
