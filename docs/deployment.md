# 部署、登录与升级

本文汇总正式部署所需的配置、平台登录与 SSO 接入方法，以及跨版本升级时需要处理的事项。快速体验见仓库根目录 [README](../README.md)。

## 生产配置要求

仓库提供的 Compose 是本地部署参考，已映射认证模式、会话密钥、安全 Cookie、运行环境和示例开关；正式部署需在 `apps/api/.env` 中显式配置这些值，并提供 HTTPS 入口。外置认证路径由 Compose 固定为挂载目录内的基础配置。完整变量见 [`.env.example`](../.env.example) 与 [`config.py`](../apps/api/src/ontofoundry_api/config.py)。

- `ONTOFOUNDRY_ENVIRONMENT=production`，`ONTOFOUNDRY_AUTH_MODE=login`，按下节配置本地账号和可选 SSO。
- 使用至少 32 字符的随机会话密钥（`ONTOFOUNDRY_SESSION_SECRET`），设置 `ONTOFOUNDRY_COOKIE_SECURE=true`、`ONTOFOUNDRY_SEED_DEMO=false`，由 HTTPS 入口提供访问。
- **修改 `ONTOFOUNDRY_MCP_TOKEN`**：默认值 `ontofoundry-mcp-default-token` 是公开的，启动检查不会拒绝它。正式环境改为至少 24 字符的随机值；不需要单空间 MCP 时显式设为空，外部即无法访问该接口。持有该令牌可按空间管理员身份读取定义、数据绑定和实例。
- 升级前备份 PostgreSQL、上传材料和连接加密密钥，按 Alembic 迁移链升级数据库。

### 数据连接

数据连接只需填写业务数据库的地址、账号和密码，密码按原样保存在平台数据库中。**业务数据库请使用只读账号**：平台对 SQL 做 sqlglot 解析和白名单检查，但这是应用层防护，不能替代数据库权限。

## 平台登录

Compose 默认使用 `login`（`apps/api/.env` 中显式设置的 `dev` 仍优先），只读挂载 [`deploy/docker/ontofoundry/`](../deploy/docker/ontofoundry/) 并指定基础配置入口。源码运行时，将 `ONTOFOUNDRY_AUTH_MODE` 改为 `login`，保留模板中的配置路径即可。默认本地账号为 `admin`／`admin123`，启动日志会提醒修改默认密码。

现场配置方法：

1. 将 `ontofoundry_config_docker.py.example` 复制为同目录的 `ontofoundry_config_docker.py`，修改 `LOCAL_USERS` 中的用户名、明文密码。基础配置不要直接修改，升级会覆盖它。
2. 需要 SSO 时，将 `custom_sso_user_info.py.example` 复制为 `custom_sso_user_info.py`，按实际返回结构映射用户信息，然后启用覆盖文件中的 `OAUTH_PROVIDERS` 和 `OAUTH_USER_INFO`。只支持一个授权码认证服务；`name` 为 1～64 位字母、数字、下划线或连字符，不能为 `local`。
3. `remote_app` 填写 `client_id`、`client_secret`、`authorize_url`、`access_token_url`、以 `/` 结尾的 `api_base_url` 和回调地址 `https://<平台域名>/api/v1/auth/callback/<name>`；`client_kwargs.scope` 缺省为 `openid profile`。将 `LOCAL_USERS` 设为空列表可关闭本地登录，但必须保留一种登录方式。
4. 限制覆盖文件和钩子文件的权限，只允许后端运行用户读取；它们已被 Git 忽略，包含的密码和客户端密钥按同等要求保管。修改后重启后端，配置不可读、导入失败或格式非法都会阻止启动。

### SSO 钩子契约

钩子必须是同步的 `oauth_user_info(provider, token_response, oauth_remotes)`，与 DataAgent 同契约，现有钩子文件可直接复用。客户端 `oauth_remotes[provider]` 已绑定基址、Bearer 访问令牌和单次请求 15 秒超时；钩子在线程中运行，不应记录令牌。返回字典必须有稳定的非空 `sub`，名称依次取 `display_name`、`preferred_username`、`name`、`email`、`sub`；可含 `email`，`role` 被忽略。异常、超时或非法返回仅使本次登录失败。

用户按用户名识别且不区分大小写：本地登录取 `LOCAL_USERS[].username`，SSO 取钩子的可选 `username`（1～120 字符，无控制字符），缺省取 `sub`。同名的本地与 SSO 登录共享用户及空间身份。新用户自动创建；平台管理员也可在首次登录前预建用户、分配空间。

### 平台管理员

`ADMIN_USERS = ["admin"]` 指定平台管理员用户名（基础配置默认值），拥有全部空间的阅读、编辑和管理权限；空列表会在启动时警告，且没有人能进入用户管理。开发模式的 `dev` 用户始终是平台管理员。

**用户名冲突风险**：认证服务返回的用户名决定用户身份；若钩子返回本地 `admin`，就会获得其空间身份，若该用户名也在 `ADMIN_USERS` 中，还会成为平台管理员。接入 SSO 前必须确认用户名可信、不会与本地账号冲突，或将本地账号改成 SSO 中不存在的名字（例如 `ontofoundry-admin`）。

## 升级说明

### 平台登录改版

- 已有用户去掉认证前缀（`dev:admin` 改为 `dev`），重名会阻止迁移并列出冲突用户名。
- **已有空间全部设为公开**，所有登录用户可阅读映射、材料、会话及实例（含业务库查询）；不希望共享的空间请在升级后改为私有。新空间默认私有。
- 回退前备份 `users` 表；降级只能为当前配置中的本地用户恢复 `local:` 前缀，无法还原其他认证服务前缀。

### 旧 OAuth 部署迁移

将模式从 `oauth` 改为 `login`，删除全部 `ONTOFOUNDRY_OAUTH_*` 环境变量（包括 `.env` 中的空值），改用 `ONTOFOUNDRY_AUTH_CONFIG`。旧字段对应如下：

| 旧变量后缀（前缀均为 `ONTOFOUNDRY_OAUTH_`） | 外置配置 |
| --- | --- |
| `PROVIDER` | `OAUTH_PROVIDERS[0]["name"]` |
| `AUTHORIZE_URL`、`TOKEN_URL` | `remote_app.authorize_url`、`remote_app.access_token_url` |
| `CLIENT_ID`、`CLIENT_SECRET` | `remote_app.client_id`、`remote_app.client_secret` |
| `REDIRECT_URI` | `remote_app.redirect_uri`，路径增加 `/<name>` |
| `USER_INFO_URL` | 在钩子中请求该地址；也可拆成 `api_base_url` 和相对路径 |

认证名称必须保持原 `PROVIDER`（默认 `internal`），钩子返回的 `sub` 必须与旧实现从 `sub` 或 `id` 解析出的标识相同，否则会创建新用户，无法保留原空间成员身份。会话密钥与 Cookie 配置继续用环境变量。本次不改数据库结构；回退时恢复旧镜像和原 OAuth 环境变量。

### 2026-11-16 MCP 地址变更

MCP 地址改为 `/api/v1/mcp`，单空间入口改为 `/api/v1/workspaces/{workspace_id}/mcp`，空间目录改为 `/api/v1/mcp/workspaces`。旧地址已删除。升级前结束所有进行中的建模运行，升级后重新发起运行以取得新的提交地址与运行凭据。外部客户端需更新完整 MCP 地址。
