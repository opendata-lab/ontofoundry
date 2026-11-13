# 平台登录实施计划

设计见[平台登录（对齐 DataAgent）](../design/2026-11-12-platform-login.md)。涉及：后端认证、前端登录页与页头、部署配置。预计 2 至 3 个工作日，先于外部智能体网关步骤二实施。

## 任务

1. **配置加载**：`services/auth_config.py` 按设计第 3、6 节加载 `ONTOFOUNDRY_AUTH_CONFIG`（目录加入模块搜索路径、导入、校验 `LOCAL_USERS`、`OAUTH_PROVIDERS`、`OAUTH_USER_INFO`），应用启动时执行，失败即启动失败；默认密码仍在使用时记警告。
2. **设置项**：`config.py` 中 `auth_mode` 改为 `dev`／`login`，删除 `oauth_*` 设置；检测到旧环境变量或 `oauth` 模式时启动失败并提示迁移；生产校验改为要求 `login`。不新增依赖。
3. **认证接口**：`api/auth.py` 按设计第 7 节实现 `options`、本地登录（明文密码用 `hmac.compare_digest` 常数时间比较）、按认证服务名的跳转与回调（复用现有 state、nonce；回调中在线程里调用钩子，`httpx.Client` 绑定 `api_base_url`、访问令牌、15 秒超时）；用户主体按第 5 节写入。
4. **部署文件**：新增 `deploy/docker/ontofoundry/` 下的基础配置、覆盖示例、钩子示例和 `.gitignore`；`compose.yaml` 只读挂载该目录并设置 `ONTOFOUNDRY_AUTH_CONFIG`；`.env.example` 删除 `ONTOFOUNDRY_OAUTH_*`，`ONTOFOUNDRY_AUTH_MODE` 说明改为 `dev`／`login`；离线包附带该目录。README 配置与迁移说明：旧 OAuth 变量如何填入配置文件，认证名称与 `sub` 必须保持不变。
5. **前端**：新增 `pages/LoginPage.tsx` 与 `/login` 路由；`api/client.ts` 在 `401` 时跳转登录页并带回原地址；页头用户名菜单增加“退出登录”（与“个人中心”同一菜单）。界面按 AGENTS.md 截图对比并运行 `npm run test:visual`。
6. **测试**：`tests/test_auth_config.py`（配置校验各失败项、默认密码警告、旧变量拒绝）、`tests/test_auth.py`（本地登录成功与失败、认证服务回调与钩子、钩子出错不影响后续登录、用户主体与迁移一致、`dev` 模式不变）、前端登录页与 `401` 跳转测试。全部修改完成后统一运行后端测试、`make lint` 和前端测试。

## 验收

| 场景 | 预期 |
|---|---|
| 使用仓库默认配置 | 登录页只显示用户名密码，`admin`／`admin123` 可登录，启动日志有默认密码警告 |
| 配置认证服务和钩子 | 登录页同时显示“通过 SSO 登录”；自研包装结构的用户信息可登录，名称正确 |
| 钩子出错 | 本次登录失败并提示，其他登录不受影响 |
| 配置错误或仍用旧 OAuth 变量 | 应用启动失败并说明原因 |
| 已有 OAuth 部署迁移 | 认证名称和 `sub` 不变时，原用户登录后仍保有空间成员身份 |
| 复用 DataAgent 钩子文件 | 不改内容即可加载 |
| `dev` 模式 | 行为不变 |

## 发布与回退

迁移在发布说明中列出：已有 OAuth 部署需把 `ONTOFOUNDRY_OAUTH_*` 的值写入 `ontofoundry_config_docker.py` 并把模式改为 `login`。回退：回到上一版本镜像并恢复原环境变量；本功能不改数据库结构。
