# AgentEvent v1

DataAgent 对外只暴露平台自己的事件模型。Pi 是执行引擎实现细节，不能成为前端协议。

数据链路：

`Pi AgentEvent -> runtime event normalizer -> AgentEvent v1 -> agent_event record -> SSE/frontend`

约束：

- 持久化记录的 `record_type` 固定为 `agent_event`；终态错误记录为 `error`。
- 事件名称由 `neutral-event.schema.json` 的闭集定义；消费者不接受引擎私有事件名。
- `tool.completed` 的 `output` / `output_meta` 由生产端一次性标准化，读取端不做历史兼容转换。
- 慢工具的存活信号使用运行时协议的 `run.heartbeat`，不写入业务事件流。
- 前端只消费 AgentEvent v1，不解析 Claude SDK 原生事件，也不识别 `pi_event` 旧别名。

文件：

- `neutral-event.schema.json`：事件信封与事件类型闭集。
- `tool-output.schema.json`：工具输出结构。
- `task-status.schema.json`：引擎结果、平台任务状态和投影关系。
