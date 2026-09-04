# 第二阶段 SQL 执行约定

SQL 按目录编号顺序执行：

1. `00_sources/`：从 Git 忽略的官方 CSV 物化本地 `raw` 层；
2. `10_staging/`：统一 0 时间、Asia/Shanghai 时间解释及质量标记；
3. `20_facts/`：订单、运单尝试、波次和 checkpoint 事实对象；
4. `30_metrics/`：唯一指标层和安全聚合输出。

所有 SQL 由 `scripts/run_phase2.py` 调度，工作目录必须是仓库根目录。本地数据库固定为 `data/local/phase2.duckdb`，整个目录被 Git 忽略。SQL 文件只包含 schema、变换逻辑和聚合口径，不包含任何原始标识符、坐标值或数据行样例。
