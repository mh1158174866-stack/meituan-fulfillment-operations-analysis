# 本地数据目录

`raw/`、`interim/` 和 `processed/` 的内容均不进入 Git，仅保留 `.gitkeep`。请使用项目脚本从美团官方仓库下载数据；不要从本项目仓库或其他第三方渠道重新分发。

第二阶段会生成 `processed/meituan_fulfillment.duckdb` 和 `interim/stage2_fingerprint.json`。DuckDB 包含明细 ID，仅供本地分析；指纹 JSON 仅含结构、行数和哈希。两者均被 Git 忽略。
