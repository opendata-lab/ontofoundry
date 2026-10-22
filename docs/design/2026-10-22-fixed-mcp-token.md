# 固定 MCP 令牌

日期：2026-10-22。状态：已确认（用户提出，采用）。

## 问题

DataAgent 通过 OntoFoundry MCP 读取本体，MCP 配置填一个固定的 `Authorization: Bearer <令牌>`。令牌应由部署方直接配置，而不是调接口生成后复制。

## 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| MT-01 | 部署时在平台环境变量 `ONTOFOUNDRY_MCP_TOKEN` 配置一个固定令牌（至少 24 个字符），DataAgent 的 MCP 鉴权头填同一个值。来源：MCP 服务常见的静态 Bearer 鉴权；属于部署配置，不进入本体模型。 | 已确认 |
| MT-02 | 固定令牌只读，固定具备 `ontology:read`、`mappings:read`、`instances:read`；只能用于带工作空间的本体接口（MCP、本体查询、导出），以该空间最早加入的管理员身份做成员检查；空间没有管理员时拒绝。不能用于空间目录接口。 | 已确认 |
| MT-03 | 外部访问只用固定令牌：删除服务令牌的签发、列表、作废接口及 `service_tokens`、`service_token_scopes` 两张表（迁移 `20261022_000003`）。留空则外部无法访问 MCP。建模运行凭据（`ofrun.`，平台每次运行自动签发、自动失效）不受影响。更换令牌：改环境变量并重启后端，同时更新 DataAgent 配置。 | 已确认 |

## 部署

离线包 `.env` 增加 `ONTOFOUNDRY_MCP_TOKEN`，compose 传给后端。DataAgent 中 OntoFoundry MCP 地址为 `<平台地址>/api/v1/ontology/workspaces/<工作空间ID>/mcp`，鉴权头 `Authorization: Bearer <ONTOFOUNDRY_MCP_TOKEN>`。
