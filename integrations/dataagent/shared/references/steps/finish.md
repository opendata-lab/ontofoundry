# 收尾：合并、修正、输出

1. 合并：`prepare_result.py --schema <schema_file> --context <context_file> --output <result_file> modeling/parts/`。定义按 draft/element_hashes、实例按 instance_baseline 自动补 before/hash，检查通过才写入。
2. 修正：最多两轮，共用 execution；只改报错片段再合并，加 --repair（平台已计次的新上下文首次不加）；耗尽保留诊断，不删计数。
3. 输出：中文说明修改、依据、实例、歧义和未交付项。写了结果就不写待确认文件，歧义在回答里给出默认处理；两者并存平台会拒收整轮。未同步表无列只提有依据的语义及空列表 Dataset，不猜映射／SQL／指标，提示“先在数据管理同步该表，再发起补齐”。技术失败不冒充业务提问或成功。
