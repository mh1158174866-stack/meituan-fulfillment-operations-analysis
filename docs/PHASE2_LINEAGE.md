# 第二阶段 SQL 血缘与执行顺序

```text
官方固定提交的四张 CSV（仅本地、Git 忽略）
  -> raw.waybill / raw.courier_wave / raw.dispatch_rider / raw.dispatch_waybill
  -> staging：时间标准化、列表拆分、质量标记
  -> facts：waybill attempt / order fulfillment / courier wave / dispatch checkpoint
  -> metrics：统一订单、时长、超时、波次负载和 checkpoint 指标
  -> reports：仅 schema、指标定义、聚合对账与测试结果
```

执行器为 `scripts/run_phase2.py`，SQL 严格按 `sql/00_sources`、`10_staging`、`20_facts`、`30_metrics` 顺序运行。本地 DuckDB 固定为 `data/local/phase2.duckdb`；数据库、CSV、Parquet、JSON 和其他明细产物均不得进入 Git。

公开报告中的聚合数值必须由指标层查询生成。后续 Python、Tableau 或报告若使用相同指标，必须读取 `metrics` schema，不得另写平行公式；Tableau 本身不在本阶段实现。
