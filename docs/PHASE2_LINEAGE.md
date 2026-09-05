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

## 文件级输入输出

| 顺序 | SQL | 输入 | 输出 |
|---:|---|---|---|
| 1 | `00_sources/00_raw_tables.sql` | 四张固定 SHA 的官方 CSV | `raw.*` 四表、`meta.build_contract` |
| 2 | `10_staging/10_waybill_attempt.sql` | `raw.waybill` | `stg.waybill_attempt`、`fact.fact_waybill_attempt` |
| 3 | `20_facts/20_order_fulfillment.sql` | `stg.waybill_attempt` | `fact.fact_order_fulfillment` |
| 4 | `10_staging/11_wave_checkpoint.sql` | 三张 wave/dispatch raw 表 | 波次成员、checkpoint 订单/骑手/在手集合 staging 表 |
| 5 | `20_facts/21_wave_checkpoint.sql` | staging 成员表、订单/waybill 事实 | 波次事实、checkpoint 两侧成员事实与汇总事实 |
| 6 | `30_metrics/30_metric_layer.sql` | 四类事实对象 | `metrics.daily_fulfillment`、`overall_fulfillment`、`checkpoint_snapshot` |
| 7 | `30_metrics/31_metric_catalog.sql` | 固定指标合同 | `metrics.metric_catalog` |

`scripts/run_phase2.py --through E` 执行两次完整 1–7，并比较逻辑数据库与公开报告哈希。`scripts/validate_phase2.py --step E` 可对现有本地数据库重复执行全部合同检查。

公开报告中的聚合数值必须由指标层查询生成。后续 Python、Tableau 或报告若使用相同指标，必须读取 `metrics` schema，不得另写平行公式；Tableau 本身不在本阶段实现。
