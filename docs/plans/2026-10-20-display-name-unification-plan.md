# 元素名称统一实施计划

依据：[已确认设计](../design/2026-10-20-display-name-unification.md)。日期：2026-10-20。

1. 完成设计、概念字段表和示例、主设计与 UI-025 修订。
2. 修改核心模型、命名空间校验、表达式/材料值引用、服务与严格提案契约；生成 JSON Schema 和 TypeScript 类型。
3. 新增清理迁移，审查所有 JSON 持久化位置并补充保留集合测试和部署步骤。
4. Ossie ZIP 与独立扩展文件、原生 ai_context.synonyms、旧外部格式兼容及转换报告；更新导入导出服务与界面。
5. 修改 MCP、DataAgent 技能/校验脚本/提示词及前端目录、详情、表单、搜索、图谱、提案与发布差异；更新所有相关测试和视觉断言。
6. 全部编辑完成后统一运行 API 全量 pytest、ruff，前端 vitest、tsc、eslint，技能测试及 generate_core_types --check。检查失败后集中修复并复跑相关检查；不要求运行沙箱不可用的 Playwright，视觉基准人工重建。
7. 中文交付报告列清理与保留表、虚构格式例子、实际测试结果、人工部署与 DataAgent 同步事项。不 commit/push，不修改排除目录。
