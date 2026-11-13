# OAuth 登录用户信息钩子

日期：2026-11-12。状态：已确认（2026-11-12 用户确认按 DataAgent 的外部脚本方式实现）。来源：现场统一认证的用户信息格式各不相同；外部智能体接入需要用户先登录才能签发个人令牌（[外部智能体接入设计](2026-11-11-runtime-agnostic-semantic-layer-for-agents.md) SL-02）。

实施见[计划](../plans/2026-11-12-oauth-login-hook-plan.md)。

## 1. 现状

`api/auth.py` 的回调用授权码换取令牌后，请求 `ONTOFOUNDRY_OAUTH_USER_INFO_URL`，固定按以下字段解析：用户标识取 `sub` 或 `id`，名称依次取 `name`、`preferred_username`、`email`，邮箱取 `email`。用户主体为 `<ONTOFOUNDRY_OAUTH_PROVIDER>:<用户标识>`。

自研认证常把用户放在包装结构里，例如 `{"code": 0, "data": {"uid": "u-1001", "nickname": "林晓"}}`。这时取不到 `sub`，登录直接失败，只能改代码适配。

DataAgent 已用外部 Python 钩子解决同一问题（opendataagent `deploy/docker/dataagent/custom_sso_user_info.py.example`、`dataagent-backend/core/auth.py`）。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| LH-01 | **外部钩子文件**：新增 `ONTOFOUNDRY_OAUTH_USER_INFO_HOOK`，指向部署方提供的 Python 文件，文件中定义 `oauth_user_info(provider, token_response, oauth_remotes)`，返回用户信息。未设置时保持现有固定解析。来源：DataAgent 的 `OAUTH_USER_INFO`；属于部署配置，不进入本体模型。 | 已确认 |
| LH-02 | **与 DataAgent 同一契约**：函数名、参数和返回字段与 DataAgent 示例一致，同一个 `custom_sso_user_info.py` 可同时用于两边。认证地址等其他配置仍用 OntoFoundry 现有环境变量，不引入 DataAgent 的 Python 配置文件。 | 已确认 |

## 3. 钩子契约

```python
def oauth_user_info(provider: str, token_response: dict, oauth_remotes: dict) -> dict: ...
```

| 参数／返回 | 说明 |
|---|---|
| `provider` | `ONTOFOUNDRY_OAUTH_PROVIDER` 的值 |
| `token_response` | 令牌端点返回的完整 JSON |
| `oauth_remotes` | `{provider: 客户端}`。客户端已带 `Authorization: Bearer <access_token>`，相对地址基于新增的 `ONTOFOUNDRY_OAUTH_API_BASE_URL` 解析，单次请求超时 15 秒；也可请求完整地址 |
| 返回 | 字典，必须含稳定、非空的 `sub`；名称取 `display_name`，缺省时依次取 `preferred_username`、`name`、`email`、`sub`；可含 `email`。`role` 等其他字段忽略：OntoFoundry 的角色属于工作空间成员关系，不来自登录 |

示例（自研认证）：

```python
def oauth_user_info(provider, token_response, oauth_remotes):
    response = oauth_remotes[provider].get("userinfo")
    response.raise_for_status()
    payload = response.json().get("data") or {}
    return {"sub": str(payload.get("uid") or ""), "display_name": payload.get("nickname") or ""}
```

用户主体仍为 `<provider>:<sub>`。已有部署改用钩子时，`sub` 必须与原先解析出的用户标识一致，否则已有用户会被当作新用户，失去原有空间成员身份。

## 4. 加载与执行

- **启动时校验**：设置了 `ONTOFOUNDRY_OAUTH_USER_INFO_HOOK` 时，文件须可读，导入成功，`oauth_user_info` 为同步函数且接受三个位置参数；任一不满足则应用启动失败并给出原因。文件所在目录加入模块搜索路径，钩子可导入同目录的辅助模块。
- **执行**：回调中在线程里调用钩子，不阻塞事件循环。钩子抛异常、超时、返回非字典或缺少 `sub` 时，本次登录失败，返回“OAuth 用户信息解析失败”，服务继续运行。
- **配置要求**：生产环境要求 `ONTOFOUNDRY_OAUTH_USER_INFO_URL` 与钩子二选一；设置钩子时用户信息地址可留空。
- **安全**：钩子是部署方代码，与环境变量同等信任，只读挂载进容器，不能通过界面上传。日志不记录 `token_response`、访问令牌和刷新令牌。

## 5. 部署

- 新增 `deploy/ontofoundry/custom_sso_user_info.py.example`（与 DataAgent 示例同契约）；实际文件 `custom_sso_user_info.py` 被忽略，不提交。
- `.env.example` 增加 `ONTOFOUNDRY_OAUTH_USER_INFO_HOOK` 和 `ONTOFOUNDRY_OAUTH_API_BASE_URL`；`compose.yaml` 给出只读挂载示例（注释状态）。
- README 配置表补充两个变量和改用钩子时的用户标识注意事项。

## 6. 不包含

- 多个认证提供方、本地账号登录、登录时映射平台角色。
- MCP 客户端的浏览器授权：已决定在网关首版之后实施，见[外部智能体接入设计](2026-11-11-runtime-agnostic-semantic-layer-for-agents.md) SL-16，依赖本设计的登录。
