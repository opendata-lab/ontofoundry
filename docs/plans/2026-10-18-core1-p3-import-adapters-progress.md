# core-1 P3 机械导入适配器实施记录

基线：main `32b56ee`；分支：`codex/core1-remaining`。本次仅本地编辑，未 commit/push，未部署或执行迁移。设计见 `docs/design/2026-10-18-core1-p3-import-adapters.md`。

## 交付范围

| 计划项 | 已实现内容 |
|---|---|
| P3-01 | `FormatAdapter`、上下文、结果、转换报告、最小显式选择；输入 SHA、确定性模型和报告共同形成内容哈希；导出/往返接口显式未启用 |
| P3-02 | 原生四字段单文件、13 份示例、目标空间 UUID 替换与元素 UUID 保留；人工证据原样保留；材料证据按 SHA 注入解析，验证行号及引文，缺材料只丢证据 |
| P3-03 | Ossie 0.2.0.dev0 ontology 与内嵌映射；原生 ZIP、独立 OSI、其他版本拒绝；UUID5 来源身份、作用域消歧、core-1 显示扩展；保留固定官方校验器和资源 |
| P3-04 | 单父文件顺序、父标识优先、标识整组转换、值类型完整祖先检查、值约束逐属性实例化、规则与全部成员分支核心校验 |
| P3-05 | 属性、二元关系、一元布尔、多元中间对象；角色顺序元组标识、完整编号属性和 direct 角色关系；缺决定角色标识整组待补全；最后角色缺标识单独报告 |
| P3-06 | Dataset 一一登记；主身份、一层 referent、平铺属性、唯一键星形附来源；直接关系、独立关系表、复合列重排、平行边及非主键唯一属性；继承绑定冲突不覆盖父绑定 |
| P3-07 | 已解析逻辑字段按 AST 改写为物理列；固定聚合、过滤 CASE、列去重、精确行计数、比率复用；其余单数据集算法保留 expression；裸 COUNT(*) 待选来源；跨数据集、查询或额外作用域 RT-69 error |
| P3-08 | 原始 A/B 样例未经预处理；03/06/07 定向源 Ossie 夹具；转换报告来源定位、确定性、错误隔离与机械结果基线 |

`adapters/ossie/__init__.py` 仍引用 P2 已删除的旧 compiler，首次实际导入适配器时暴露此问题；本次删除该悬空导出，公开能力改由显式适配器选择提供。未改变运行时 API 和核心模型。

## 语义边界验证

- 成员定义有任一分支无法解析时，整项 RT-31 error，不导入剩余分支；简单条件保持结构化，EXISTS 保留表达式与方向。
- 组合标识缺成员不裁剪；子对象本地编号不覆盖已有父标识；多元决定角色缺标识不使用随机 UUID 填充。
- 字段、映射或指标的局部错误不影响独立条目；重复来源名称不任取第一项；输出的全部 target ids 必须存在于最终核心图。
- 同一业务关系的全部候选绑定先汇总，再判断唯一性；出现不同绑定时全部报告，不任取首项或末项。重复指标名和不等价的多个对象主来源也不按顺序选择。
- 复合键按目标声明次序配对；复合唯一键不拆成多个唯一属性，声明的单列唯一键可以恢复对应直接绑定属性的唯一性。
- 真实 SQLite 两行数据 `[NULL, 10]` 上验证导入的 `COUNT(列)` 结果为 1；对应行计数仍为 simple count，不改为去重或非空计数。
- 比率分量即使在比率之后声明也能匹配；没有唯一已登记分量时保留单条 expression，不新增分量。
- 上传字节 SHA 与两空格格式化材料 SHA 区分；定位对应实际 JSON pointer 及格式化行范围。JSON 解析失败只记录真实行列，不伪造 pointer。

## 统一验证

工作目录：本工作树的 `apps/api`；Python 3.13.4。使用 `uv sync --python 3.13 --all-extras --dev` 建立隔离依赖，没有启动数据库或应用服务。

```sh
uv run --python 3.13 pytest -q tests/test_core1_ossie_import.py tests/test_core1_native_import.py tests/test_core1_translation_report.py tests/test_core1_architecture.py
uv run --python 3.13 pytest -q -rs
uv run --python 3.13 ruff check src tests
uv run --python 3.13 ruff format --check src tests
uv run --python 3.13 python -m ontofoundry_api.contracts.export_schema --check
uv run --python 3.13 pytest -q ../../integrations/dataagent/skills/ontofoundry-modeling/tests
```

定向适配器与架构检查：**94 passed、0 failed、0 errors、0 skipped**。ruff check、format（161 个文件）与 Schema 漂移检查通过；建模技能测试 **3 passed**。完整后端最终结果：**801 passed、0 failed、0 errors、13 skipped**，共 814 项，54.12 秒。跳过项为既有 PostgreSQL 11 项、MySQL 2 项；未把跳过记为通过。

本轮没有配置一次性 PostgreSQL/MySQL，既有外部系统测试按约定跳过；P3 本身为纯转换库，其新增测试全部实际执行。运行仅使用测试自建的内存 SQLite 验证计数语义，不连接开发、生产或业务数据库。

首轮发现并修复适配器包的悬空 compiler 导入；校正 A 样例不含 ontology_mappings、无法闭合成员定义使用 RT-31 的测试预期。原 A/B 文件未修改，核心语义断言没有放宽。

最终全量检查后仅补记录，未再修改实现。`git diff --check` 通过。告警共 3 项：既有 Starlette/httpx、anyio 两项弃用提示，以及按设计保留的 `TranslationIssue.construct` 与 Pydantic 方法同名提示；报告的 JSON 序列化与确定性检查通过。

## 未执行与后续

- 本期无前端改动，未重复前端构建、截图或局域网验收。
- P4 尚未实施：材料/报告持久化、preview/confirm、匹配及引用重写、pending 提案、人工补全和导入界面。
- P5 尚未实施：导出、下载、官方目标文件校验、定向往返；`export_document`、`diff_roundtrip` 显式拒绝调用。
- DataAgent 管理后台同步、技能安装、重启、开发/生产数据库迁移及环境端到端验收均未执行。
- 结构化 OR 多分支、多跳条件编辑按用户确认降低优先级，不阻塞本期。
