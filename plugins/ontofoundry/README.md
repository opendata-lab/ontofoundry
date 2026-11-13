# OntoFoundry 插件

让外部智能体（Claude Code、ZCode、opencode、Codex）在回答业务数据问题前读取 OntoFoundry 已发布的本体定义，并把用户对口径的纠正记录回平台。插件不含本地工具代码，工具全部来自 OntoFoundry 的 MCP 接口；业务取数仍用客户端自己的查询工具。

内容：

- `.mcp.json`：MCP 地址与 `Authorization` 头，取自插件配置项 `ontofoundry_mcp_url`、`ontofoundry_token`。
- `skills/ontology-grounding/SKILL.md`：检索、精读、按定义生成查询、版本与本地缓存、反馈规则。

## 准备

- **地址**：`https://<平台域名>/api/v1/ontology/mcp`（外部智能体网关）。
- **令牌**：登录平台，页头用户名 →“个人中心”→“个人令牌”签发，只显示一次。

> 网关和个人令牌随实施计划步骤二上线。上线前只在隔离环境试点：地址填单空间入口 `/api/v1/ontology/workspaces/<空间 ID>/mcp`，令牌用部署时设置的 `ONTOFOUNDRY_MCP_TOKEN`。

## Claude Code

```text
/plugin install ontofoundry --marketplace opendata-lab/ontofoundry
```

安装时按提示填写地址和令牌（令牌按敏感项保存）。无法访问 GitHub 时，把离线包中的仓库目录作为本地插件目录：`/plugin marketplace add <本地目录>`。

## ZCode

在插件设置中“添加插件目录”，选择 GitHub 仓库 `opendata-lab/ontofoundry` 或离线包中的本地目录，安装 `ontofoundry`。ZCode 读取 `.claude-plugin/plugin.json`，不需要另一份清单。

## opencode

opencode 不读取插件包，分别配置 Skill 和 MCP：

1. 把 `skills/ontology-grounding` 复制或链接到 `.opencode/skills/`（或 `.claude/skills/`、`.agents/skills/`）。
2. 在 `opencode.json` 中加入：

```json
{
  "mcp": {
    "servers": {
      "ontofoundry": {
        "type": "remote",
        "url": "https://<平台域名>/api/v1/ontology/mcp",
        "oauth": false,
        "headers": { "Authorization": "Bearer {env:ONTOFOUNDRY_TOKEN}" }
      }
    }
  }
}
```

然后在环境变量 `ONTOFOUNDRY_TOKEN` 中设置令牌。

## Codex

Codex 不读取插件包，分别配置 Skill 和 MCP：

1. 把 `skills/ontology-grounding` 复制或链接到项目的 `.agents/skills/`（Codex 从当前目录向上到仓库根目录查找）；个人全局使用时放在 `~/.agents/skills/`。
2. 在 `~/.codex/config.toml` 中加入，并在环境变量 `ONTOFOUNDRY_TOKEN` 中设置令牌：

```toml
[mcp_servers.ontofoundry]
url = "https://<平台域名>/api/v1/ontology/mcp"
bearer_token_env_var = "ONTOFOUNDRY_TOKEN"
```

## 更新

修改插件内容后同步提高 `.claude-plugin/plugin.json` 的 `version`，客户端据此提示更新。
