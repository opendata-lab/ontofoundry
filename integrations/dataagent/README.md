# DataAgent 集成包

OntoFoundry 的 Agent 能力全部运行在外部 OpenDataWorks DataAgent 上。本目录是
OntoFoundry 这一侧维护、由管理员在 DataAgent 管理端手工安装的内容。

**OntoFoundry 不会自动创建 Agent 或 Skill**，它只通过 `ONTOFOUNDRY_DATAAGENT_AGENT_ID`
引用一个已存在的 `agent_id`。自动创建意味着 OntoFoundry 需要 DataAgent 的管理权限，
那会让"复用运行时"重新变回"拥有运行时"。

```
integrations/dataagent/
├── skills/md2ossie/             Skill 源码，唯一真相，纳入版本控制
├── agents/agent_ontofoundry.md  Agent 定义参考
├── Makefile                     make zip → dist/md2ossie.zip
└── dist/                        生成产物，不提交
```

## 安装步骤

按顺序执行。每一步都有对应的失败现象，照着排查即可。

### 1. 建站点并生成服务端接入密钥

DataAgent 管理端 → Widget 接入设置 → 新建站点：

| 字段 | 值 |
| --- | --- |
| `website_id` | `ontofoundry` |
| `allowed_origins` | **留空** |
| 服务端接入 | **开启**，并生成 access key |

`allowed_origins` 留空是对的：OntoFoundry 从服务端发起调用，不带 `Origin`。
恰恰因此必须开启服务端接入——否则任何能连到 DataAgent 的进程只要知道
`website_id` 就能创建会话。

**access key 的明文只显示一次**，当场复制。

> 失败现象：站点没建 → OntoFoundry 报 "DataAgent 拒绝了本站点"；密钥没配或不匹配
> → "DataAgent 拒绝了服务端接入密钥"。

### 2. 导入 md2ossie Skill

```sh
make -C integrations/dataagent zip
```

把产出的 `dist/md2ossie.zip` 上传到管理端的 Skill 导入。管理端**只接受 ZIP**，
不接受目录；归档根目录是 `md2ossie/`，`Makefile` 已经保证了这个结构。

ZIP 不提交进 Git：源码目录是唯一真相，提交二进制会让 diff 不可读并产生第二份真相。

### 3. 创建 Agent

按 [`agents/agent_ontofoundry.md`](./agents/agent_ontofoundry.md) 创建，`agent_id`
必须是 `agent_ontofoundry`。

**两件最容易漏的事**，那份文档里都写明了原因：

- **可见性必须设为"全部可见"。** Widget 身份不是 DataAgent 的登录用户，受限可见的
  Agent 对它等同于不存在。
- **系统提示词必须包含结果文件约定。** 缺了它，Agent 只会用自然语言回答，不写结果
  文件，右侧候选区永远是空的——而任务看起来是成功的。

### 4. 配置 OntoFoundry

在部署环境设置：

| 变量 | 值 |
| --- | --- |
| `ONTOFOUNDRY_DATAAGENT_BASE_URL` | 外部 DataAgent 地址 |
| `ONTOFOUNDRY_DATAAGENT_API_PREFIX` | `/api/v1/nl2sql`（默认值，一般不用改） |
| `ONTOFOUNDRY_DATAAGENT_WEBSITE_ID` | `ontofoundry` |
| `ONTOFOUNDRY_DATAAGENT_ACCESS_KEY` | 第 1 步生成的明文 |
| `ONTOFOUNDRY_DATAAGENT_AGENT_ID` | `agent_ontofoundry` |
| `ONTOFOUNDRY_DATAAGENT_REQUEST_TIMEOUT_SECONDS` | `30` |

凭据只经部署环境注入，**不进数据库、不经浏览器**。设置页只读展示连通性，不提供
密钥输入框。

DataAgent 必须只暴露在可信内网。access key 是纵深防御的一层，不是把它放到公网的许可。

### 5. 验证

打开 OntoFoundry 的空间设置页，确认 "DataAgent 连通性" 四项全绿：配置完整性、
连通性、站点放行、Agent 存在性。

任何一项报红都会同时给出修复指引。

## 回滚清理

OntoFoundry 的数据库回滚**不会**删除已经在 DataAgent 上创建的 Topic。若执行了回滚，
到管理端按 `website_id=ontofoundry` 筛选，删除该时间窗内创建的 Topic，否则它们会成为
无主会话。

每个建模会话在管理端呈现为一个独立的"外部用户"（`ontofoundry:{workspace_id}:{session_id}`）。
这是刻意的：DataAgent 按 `external_user_id` 做会话隔离，若用真实用户 ID，同一个建模
会话就无法被空间内第二个成员打开。
