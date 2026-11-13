# 平台登录（对齐 DataAgent）

日期：2026-11-12。状态：已确认。来源：现场统一认证的接入方式各不相同，SSO 未就绪时也要能登录；外部智能体接入需要用户先登录才能签发个人令牌（[外部智能体接入设计](2026-11-11-runtime-agnostic-semantic-layer-for-agents.md) SL-02）。做法沿用 opendataagent 的外置 Python 配置（`deploy/docker/dataagent/dataagent_config.py`、`dataagent-backend/core/auth.py`）。

实施见[计划](../plans/2026-11-12-platform-login-plan.md)。先于外部智能体网关实施。

## 1. 现状

- `ONTOFOUNDRY_AUTH_MODE=dev`：不登录，自动使用开发用户。
- `ONTOFOUNDRY_AUTH_MODE=oauth`：直接跳转到 `ONTOFOUNDRY_OAUTH_*` 环境变量配置的一个认证服务；回调按固定字段解析用户信息（`sub` 或 `id`，名称取 `name`、`preferred_username`、`email`）。
- 没有登录页，没有本地账号。自研认证返回包装结构（如 `{"code": 0, "data": {"uid": ...}}`）时无法登录，SSO 未就绪时也无法登录。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| PL-01 | **外置 Python 配置文件**：`ONTOFOUNDRY_AUTH_CONFIG` 指向配置文件，内容与 DataAgent 同形：`LOCAL_USERS`、`OAUTH_PROVIDERS`（一个）、`OAUTH_USER_INFO`。删除 `ONTOFOUNDRY_OAUTH_*` 环境变量，已有部署迁移一次。来源：opendataagent 外置配置；属于部署配置，不进入本体模型。 | 2026-11-12 用户确认 |
| PL-02 | **本地账号**：登录页提供用户名、密码登录，账号在 `LOCAL_USERS` 中以明文密码配置，与同一文件中的 `client_secret` 同等保管；不使用 bcrypt 哈希，免去现场生成哈希的步骤（DataAgent 用 bcrypt，此处有意不同）。仓库自带默认账号 `admin`／`admin123`，与 DataAgent 一致，现场应自行修改。 | 2026-11-12 用户确认；明文密码 2026-11-12 用户决定 |
| PL-03 | **登录页**：未登录时显示登录页，含本地登录表单和“通过 <认证名称> 登录”按钮，二者按配置显示。 | 2026-11-12 用户确认 |
| PL-04 | **用户信息钩子**：配置了 `OAUTH_PROVIDERS` 时必须提供 `OAUTH_USER_INFO(provider, token_response, oauth_remotes)`，契约与 DataAgent 相同，同一个 `custom_sso_user_info.py` 两边通用。 | 2026-11-12 用户确认 |

不沿用 DataAgent 的 `ADMIN_USERS` 和角色字段：OntoFoundry 的权限来自工作空间成员关系，登录不授予平台角色。会话密钥、Cookie 名称与安全属性仍用现有环境变量（`ONTOFOUNDRY_SESSION_SECRET` 等），不搬进配置文件。

## 3. 配置文件

文件位置与加载方式沿用 DataAgent：

```text
deploy/docker/ontofoundry/
  ontofoundry_config.py                 仓库自带的基础配置（默认值），不要直接修改
  ontofoundry_config_docker.py.example  现场覆盖示例；复制为 ontofoundry_config_docker.py 后生效
  custom_sso_user_info.py.example       用户信息钩子示例，与 DataAgent 示例同契约
  .gitignore                            忽略 ontofoundry_config_docker.py、custom_sso_user_info.py
```

基础配置末尾在同目录存在 `ontofoundry_config_docker.py` 时 `from ontofoundry_config_docker import *`，现场只写需要覆盖的项。加载器把配置文件所在目录加入模块搜索路径。compose 把该目录只读挂载进后端容器，并设置 `ONTOFOUNDRY_AUTH_CONFIG`。

```python
# ontofoundry_config_docker.py（现场覆盖示例）
LOCAL_USERS = [
    {"username": "admin", "password": "换成现场自己的密码"},
]
OAUTH_PROVIDERS = [{
    "name": "SSO",                      # 登录按钮名称，也是用户标识前缀
    "remote_app": {
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "authorize_url": "https://sso.example.com/oauth/authorize",
        "access_token_url": "https://sso.example.com/oauth/token",
        "api_base_url": "https://sso.example.com/oauth/",
        "client_kwargs": {"scope": "openid profile"},
        "redirect_uri": "https://ontofoundry.example.com/api/v1/auth/callback/SSO",
    },
}]
from custom_sso_user_info import oauth_user_info
OAUTH_USER_INFO = oauth_user_info
```

| 项 | 规则 |
|---|---|
| `LOCAL_USERS` | 列表，每项 `username`（非空，唯一）和 `password`（非空明文）。基础配置含 `admin`／`admin123`；置为空列表即关闭本地登录。覆盖文件含明文密码和 `client_secret`，只读挂载、不入库，文件权限限制为后端运行用户可读 |
| `OAUTH_PROVIDERS` | 0 或 1 项。`name` 为 1～64 位字母、数字、下划线或连字符，不能为 `local`；`remote_app` 必须有 `client_id`、`client_secret`、`authorize_url`、`access_token_url`、`api_base_url`（以 `/` 结尾，钩子客户端的基址）、`redirect_uri`（路径必须是 `/api/v1/auth/callback/<name>`）；只支持授权码模式 |
| `OAUTH_USER_INFO` | 配置了认证服务时必填；同步函数，接受 `(provider, token_response, oauth_remotes)` |

## 4. 钩子契约

| 参数／返回 | 说明 |
|---|---|
| `provider` | `OAUTH_PROVIDERS[0]["name"]` |
| `token_response` | 令牌端点返回的完整 JSON |
| `oauth_remotes` | `{provider: 客户端}`，客户端已带 `Authorization: Bearer <access_token>`，相对地址基于 `api_base_url`，单次请求超时 15 秒 |
| 返回 | 字典，必须含稳定、非空的 `sub`；名称取 `display_name`，缺省时依次取 `preferred_username`、`name`、`email`、`sub`；可含 `email`；`role` 忽略 |

钩子在线程中执行。抛异常、超时、返回非字典或缺 `sub` 时本次登录失败，服务继续运行；日志不记录 `token_response` 和任何令牌。

## 5. 用户与会话

| 登录方式 | 用户主体（`users.subject`） | 显示名 |
|---|---|---|
| 本地账号 | `local:<username>` | `username` |
| 认证服务 | `<provider>:<sub>` | 钩子返回的名称 |

登录成功后沿用现有会话 Cookie。新用户没有任何空间成员身份，由空间管理员添加，与现在一致。

已有 OAuth 部署迁移时，`OAUTH_PROVIDERS[0]["name"]` 必须等于原 `ONTOFOUNDRY_OAUTH_PROVIDER`（默认 `internal`），钩子返回的 `sub` 必须等于原先解析出的用户标识，否则已有用户会被当作新用户，失去原有空间成员身份。

## 6. 模式与校验

| `ONTOFOUNDRY_AUTH_MODE` | 行为 |
|---|---|
| `dev` | 不变：不登录，开发用户；不读取配置文件 |
| `login`（替代 `oauth`） | 必须设置 `ONTOFOUNDRY_AUTH_CONFIG`，且至少配置一种登录方式 |

启动时校验，任一不满足即启动失败并说明原因：文件可读且能导入；各项格式符合第 3 节；配置了认证服务却缺少钩子，或钩子不是同步函数、参数不符；仍设置了已删除的 `ONTOFOUNDRY_OAUTH_*` 环境变量或 `ONTOFOUNDRY_AUTH_MODE=oauth`（提示迁移）。生产环境要求 `login`。

`admin` 仍使用默认密码 `admin123` 时，启动日志输出警告，登录不受影响。

## 7. 接口与页面

| 接口 | 说明 |
|---|---|
| `GET /api/v1/auth/options` | 登录页所需信息：`{"local_login": true, "oauth": {"name": "SSO"} 或 null}`，不需登录 |
| `POST /api/v1/auth/login/local` | `{"username", "password"}`，密码用常数时间比较；成功建立会话返回 `204`；失败返回 `401`“用户名或密码错误”，不区分用户是否存在，日志记录用户名 |
| `GET /api/v1/auth/login/{provider}` | 跳转到认证服务（沿用现有 state 与 nonce 校验） |
| `GET /api/v1/auth/callback/{provider}` | 换取令牌、调用钩子、建立会话后回到原页面；state 校验通过后失败时跳转 `/login?error=oauth_denied`、`oauth_exchange_failed` 或 `oauth_user_info_failed`，登录页显示对应提示（同 DataAgent） |
| `POST /api/v1/auth/logout` | 不变 |

登录页 `/login`：标题“OntoFoundry”，按 `options` 显示用户名密码表单和“通过 SSO 登录”按钮（两者都有时中间用“或”分隔），使用 Ant Design 表单和现有设计变量。前端收到 `401` 时跳转登录页，登录后回到原页面。页头用户名菜单增加“退出登录”。

## 8. 不包含

- 多个认证服务、平台级管理员、登录失败锁定。
- MCP 客户端的浏览器授权：见外部智能体接入设计 SL-16，依赖本设计的登录。
