# OAuth 登录用户信息钩子实施计划

设计见 [OAuth 登录用户信息钩子](../design/2026-11-12-oauth-login-hook.md)。涉及：后端认证、部署配置。预计 1 个工作日。先于外部智能体网关的步骤二实施。

## 任务

1. `config.py`：新增 `oauth_user_info_hook: Path | None`、`oauth_api_base_url: str`；生产校验改为用户信息地址与钩子二选一。
2. `services/oauth_hook.py`：按设计第 4 节加载并校验钩子（可读、可导入、同步、三个参数），应用启动时调用一次，失败即启动失败；提供在线程中执行钩子的函数，统一把异常、超时、非字典、缺 `sub` 转为登录失败。
3. `api/auth.py` 回调：设置了钩子时，用 `httpx.Client`（`base_url` 为 `oauth_api_base_url`，带访问令牌，超时 15 秒）组成 `oauth_remotes` 调用钩子并按第 3 节取 `sub`、名称和邮箱；未设置时保持现有解析。日志不记录令牌。
4. 部署：新增 `deploy/ontofoundry/custom_sso_user_info.py.example` 与忽略实际文件的 `.gitignore`；`.env.example` 与 `compose.yaml` 补充变量和只读挂载示例；README 配置表补充说明。
5. 测试（`tests/test_auth.py` 及新增 `tests/test_oauth_hook.py`）：
   - 无钩子时现有登录行为不变；
   - 钩子解析包装结构返回 `sub` 与名称，用户主体为 `<provider>:<sub>`，再次登录更新名称不新建用户；
   - 名称缺省回退顺序；
   - 钩子抛异常、返回非字典、缺 `sub` 时登录失败且服务可继续登录；
   - 启动校验：文件不存在、导入失败、异步函数、参数不符各自报错；
   - 同一个 DataAgent 示例文件可直接加载。
6. 全部修改完成后统一运行后端测试和 `make lint`。

## 验收

| 场景 | 预期 |
|---|---|
| 未配置钩子 | 现有 OAuth 登录不变 |
| 配置自研认证钩子 | 包装结构的用户信息能登录，名称正确 |
| 钩子出错 | 本次登录失败并提示，其他用户登录不受影响 |
| 钩子配置错误 | 应用启动失败并说明原因 |
| 复用 DataAgent 钩子文件 | 不改内容即可加载 |

## 发布与回退

新增配置均可选，未设置时行为不变。回退：去掉 `ONTOFOUNDRY_OAUTH_USER_INFO_HOOK` 后重启。
