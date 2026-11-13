# 用户管理与空间公开实施计划

设计见[用户管理与空间公开](../design/2026-11-12-user-management.md)。在平台登录（PR #54、#55）合并之后实施，分两个 PR：后端一个、前端一个。预计 5 至 6 个工作日。

## 任务

1. **迁移**：Alembic 迁移把 `users.subject` 改名为 `username`，唯一索引改为 `lower(username)`，新增 `last_login_at`；新增 `workspaces.is_public`，已有空间为 `true`，新建默认 `false`；按设计第 6 节去掉已有数据的前缀，`dev:admin` 改为 `dev`，重名时迁移失败并列出冲突。
2. **登录**：`services/auth.py` 本地登录按 `username`、SSO 按钩子的 `username`（缺省 `sub`）查找或创建用户，用户名比较不区分大小写；登录成功写 `last_login_at`。钩子校验增加可选 `username`。`dev` 用户用户名为 `dev`。
3. **配置**：`services/auth_config.py` 读取并校验 `ADMIN_USERS`，为空时记警告；基础配置和覆盖示例加入 `ADMIN_USERS = ["admin"]`；README 写明 UM-01 的用户名冲突风险。
4. **权限与最后管理员规则**：服务层新增 `is_platform_admin(username)`；`services/access.py` 集中 `can_read_workspace`／`can_edit_workspace`／`can_manage_workspace`（平台管理员全部通过），角色校验加入 `viewer`；空间成员的增、改角色、删统一走一个服务函数，检查“至少一名管理员”（平台管理员不计入），违反抛 `ConflictError`。
5. **空间公开**：`services/access.py` 新增 `can_read_workspace`（成员或公开）；逐个读接口（本体、映射、材料、会话、实例、数据连接、导出、概览）改用它，写接口由 `require_member` 改为 `can_edit_workspace`，管理接口改为 `can_manage_workspace`；`GET /workspaces` 只返回成员和公开空间；`PATCH /workspaces/{id}` 接受 `is_public`。写一张读接口清单测试：每个读接口对公开空间非成员返回 `200`，对私有空间非成员返回 `403`／`404`，每个写接口对非成员和可查看成员返回 `403`、对平台管理员返回成功；`GET /workspaces` 对平台管理员返回全部空间。网关成员检查改为 `can_read_workspace`。
6. **接口**：按设计第 6 节新增 `/api/v1/admin/*`、`/api/v1/me/workspaces`、`/api/v1/workspaces/{id}/users/search`，`/auth/me` 增加字段，空间成员添加改为 `user_id`。同步 `contracts/` 的 JSON Schema、Pydantic 模型和前端类型。
7. **前端**：空间设置增加“公开”开关（说明：所有登录用户可阅读本空间全部内容）；目录页标“公开”；非成员进入公开空间时显示全部阅读页面、隐藏编辑操作。页头用户菜单增加“个人中心”“用户管理”（按 `is_platform_admin` 显示）；新增 `/me`（个人信息页签）和 `/admin/users`（列表、搜索、新建用户、分配空间抽屉）；空间设置添加成员改为按用户名搜索并选择角色（可查看／可编辑／管理员），成员列表可改角色；可查看成员与公开空间非成员一样隐藏编辑操作。按 AGENTS.md 截图对比，运行 `npm run test:visual`。
8. **测试**：迁移（去前缀、重名失败）；本地与 SSO 同名登录到同一用户并共享空间身份；预建用户首次 SSO 登录后保有分配的空间；钩子返回 `username` 与只返回 `sub` 两种情况；非平台管理员访问 `/admin/*` 得到 `403`；最后一名管理员不能被移除或降级；前端菜单显示条件、用户管理页和分配抽屉。全部修改完成后统一运行后端测试、`make lint` 和前端测试。

## 验收

| 场景 | 预期 |
|---|---|
| 平台管理员预建 `lisi`，分配到“星河零售”为成员；李四通过 SSO 登录（钩子返回 `username: "lisi"`） | 登录后直接看到“星河零售”，用户管理中“最近登录”更新 |
| 钩子只返回 `sub: "8f3a-91c2"` | 用户名为 `8f3a-91c2` |
| 本地账号 `zhangsan` 与 SSO 返回 `zhangsan` | 同一用户，空间身份相同 |
| 未预建的 `wangwu` 首次 SSO 登录 | 自动创建，没有空间，出现在用户列表中 |
| 非 `ADMIN_USERS` 用户 | 菜单中没有“用户管理”，直接访问接口得到 `403` |
| 移除某空间唯一的管理员 | 提示“该空间至少需要一名管理员”，不生效 |
| 空间管理员添加尚未登录的预建用户 | 可以添加 |
| 已有数据库升级 | `local:admin` 变为 `admin`，原空间身份保留；已有空间均为公开 |
| 王五（非成员）打开公开的“星河零售” | 能看映射、材料、会话和实例，没有编辑按钮；调用写接口得到 `403` |
| 管理员把“星河零售”改为私有 | 王五的目录中不再出现，直接访问显示无权访问；其外部智能体 `list_spaces` 中也消失 |
| 新建空间 | 默认私有 |
| admin（`ADMIN_USERS`）打开未加入的私有空间“云帆财务” | 目录中可见；可阅读、编辑、改空间设置和成员；成员列表中不出现 admin |
| 空间管理员把 lisi 加为“可查看” | lisi 能看到该私有空间全部内容，没有编辑按钮，写接口 `403` |
| 空间管理员在空间设置中搜索不存在的用户名 | 提示联系平台管理员创建，无新建入口 |

## 发布与回退

发布说明写明：升级后已有空间全部公开，所有登录用户可阅读其映射、材料、会话和实例，不希望共享的空间请空间管理员改为私有；用户按用户名识别；接入 SSO 前确认钩子返回的用户名不与本地账号冲突；`ADMIN_USERS` 默认是 `admin`。回退：迁移的 downgrade 把 `username` 改回 `subject`，本地用户加回 `local:` 前缀，其余用户无法还原原认证服务前缀，回退前需备份 `users` 表。
