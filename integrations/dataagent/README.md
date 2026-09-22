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

### 2. 安装 md2ossie Skill

Skill 由 DataAgent 在**启动时从 `SKILLS_ROOT_DIR` 扫描索引**，没有 ZIP 上传接口。
把源码目录放进去，然后重启 DataAgent：

```sh
cp -r integrations/dataagent/skills/md2ossie "$SKILLS_ROOT_DIR"/
# 重启 DataAgent 让它重新索引
```

确认已识别：

```sh
curl -s http://<dataagent>/api/v1/dataagent/agents/capabilities \
  | python3 -c "import sys,json;print([s['folder'] for s in json.load(sys.stdin)['skills']])"
```

**顺序不能反。** 先启动后放目录的话，下一步创建 Agent 会报
`unknown skill folder: md2ossie`——我就是这么踩的。

`make -C integrations/dataagent zip` 仍然可用，但那是给需要分发归档的场景，
本地安装用不上。

### 3. 创建 Agent

按 [`agents/agent_ontofoundry.md`](./agents/agent_ontofoundry.md) 创建，`agent_id`
由服务端生成，**不是调用方指定的**——创建接口会返回形如
`agent_7895f271d13c40f9bc2fabf7` 的 ID。把返回的那个值填进
`ONTOFOUNDRY_DATAAGENT_AGENT_ID`，不要照抄本文档里的示例名。

**三件最容易漏的事**，前两件那份文档里写明了原因，第三件是实测踩出来的：

- **可见性必须设为"全部可见"。** Widget 身份不是 DataAgent 的登录用户，受限可见的
  Agent 对它等同于不存在。
- **`max_turns` 至少给到 100。** `md2ossie` 要先读完 Ossie 规范文档、再分析表结构、
  最后生成完整 Ossie JSON。默认值或几十轮不够用——Agent 会在读规范的阶段耗尽轮次，
  任务以 `finished` 结束却没写结果文件。现象和下面那条一模一样：**任务显示成功，
  新版本草稿没有变化，也没有任何报错**。我第一次配 30 轮就是这么失败的。

- **系统提示词必须包含结果文件约定。** 缺了它，Agent 只会用自然语言回答，不写结果
  文件，右侧新版本草稿不会更新——而任务看起来是成功的。

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
